"""Local dashboard for the collected trends. Usage: python launch.py (app window) or streamlit run dashboard.py

Reads trends.db directly and ranks with predict.py, so it always shows the latest run. Read-only.
"""
import os
import threading
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from collect import RSS_GEOS, TARGET, connect, load_keywords, tracked
from predict import predict


def last_run(con):
    (ts,) = con.execute("SELECT max(fetched_at) FROM trending").fetchone()
    return datetime.fromisoformat(ts).astimezone().strftime("%d %b %Y %H:%M") if ts else "never"  # PC's local time


def keyword_series(con, keyword, source):
    """Weekly 0-100 interest abroad vs Indonesia, one column each, indexed by date."""
    df = pd.read_sql_query(
        "SELECT date, geo, value FROM interest WHERE keyword = ? AND geo IN (?, ?) AND value IS NOT NULL ORDER BY date",
        con, params=(keyword, source, TARGET))
    wide = df.pivot_table(index="date", columns="geo", values="value")
    wide.index = pd.to_datetime(wide.index)  # real dates, so the chart axis isn't one label per week
    return wide.rename(columns={source: f"abroad ({source})", TARGET: "Indonesia"})


def latest_trending(con, geo):
    df = pd.read_sql_query(
        "SELECT term, approx_traffic AS traffic, news_title AS news, pub_date AS published FROM trending "
        "WHERE geo = ? ORDER BY pub_date DESC LIMIT 20", con, params=(geo,))
    local = datetime.now().astimezone().tzinfo
    df["published"] = pd.to_datetime(df["published"], utc=True).dt.tz_convert(local).dt.strftime("%d %b %H:%M")
    df["news"] = df["news"].fillna("")
    return df


def quit_button():
    """Started from the launcher there is no terminal to stop it from (same as data-analyst-agent)."""
    if not st.button("⏻ Quit app", width="stretch"):
        return
    st.success("The app has stopped. You can close this window.")
    # hide Streamlit's "Connection error" pop-up, then close the launcher's app window
    st.markdown("<style>[data-testid='stDialog'], [data-testid='stStatusWidget'] {display: none !important}"
                "</style>", unsafe_allow_html=True)
    components.html("<script>setTimeout(function(){try{window.top.close()}catch(e){}}, 400)</script>", height=0)
    threading.Timer(1.0, lambda: os._exit(0)).start()  # let the message reach the browser first


def main():
    st.set_page_config(page_title="Trend Collector", page_icon="📈", layout="wide")
    con = connect()
    rows = predict(con, tracked(con, load_keywords()))
    ranked = pd.DataFrame(rows)

    with st.sidebar:
        st.header("📈 Trend Collector")
        st.caption("Spots fads rising abroad before they go viral in Indonesia.")
        st.caption(f"Last collected: **{last_run(con)}**")
        st.caption("New data arrives automatically after the PC starts and every 24 h.")
        if st.button("↻ Refresh", width="stretch"):
            st.rerun()
        if os.getenv("TC_LAUNCHER"):
            quit_button()

    st.title("Indonesia's next viral trend")
    if ranked.empty:
        st.info("No data yet. The collector runs a few minutes after the PC starts; check back then.")
        return

    top = ranked.iloc[0]
    rising = ranked["stage"].isin(["rising in Indonesia", "first signs in Indonesia"]).sum()
    waiting = (ranked["stage"] == "growing abroad, not in Indonesia yet").sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Top pick", top["keyword"], top["stage"], delta_color="off")
    c2.metric("Starting in Indonesia", int(rising))
    c3.metric("Growing abroad, not here yet", int(waiting))
    c4.metric("Keywords tracked", len(ranked))

    tab_rank, tab_chart, tab_trending = st.tabs(["🏆 Ranking", "📊 Interest over time", "🔥 Trending now"])
    with tab_rank:
        st.caption("Score is a heuristic: growing abroad + starting to grow in Indonesia scores highest.")
        st.dataframe(ranked, hide_index=True, width="stretch",
                     column_config={"growth_abroad": st.column_config.NumberColumn("growth abroad", format="x%.2f"),
                                    "growth_indonesia": st.column_config.NumberColumn("growth Indonesia",
                                                                                      format="x%.2f")})
    with tab_chart:
        pick = st.selectbox("Keyword", ranked["keyword"])
        row = ranked[ranked["keyword"] == pick].iloc[0]
        st.caption(f"Stage: **{row['stage']}** · Google scales each line to its own peak (100), "
                   "so compare shapes, not heights")
        st.line_chart(keyword_series(con, pick, row["source"]))
    with tab_trending:
        geo = st.radio("Country", RSS_GEOS, horizontal=True)
        st.dataframe(latest_trending(con, geo), hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
