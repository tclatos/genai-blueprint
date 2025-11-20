import asyncio

import streamlit as st
from browser_use import Agent, BrowserSession
from genai_tk.core.llm_factory import get_llm
from streamlit import session_state as sss

LLM_ID = "gpt_4o_azure"

st.title("Browser Control demo (Work in Progress)")

# Initialize session state
if "agent" not in sss:
    sss.agent = None
if "running" not in sss:
    sss.running = False
if "agent_history" not in sss:
    sss.agent_history = None


with st.container():
    task = st.text_input("Task:", key="task", value="Compare the price of gpt-4o and DeepSeek-V3")

    col1, col2, col3 = st.columns(3)
    headless = col3.checkbox("Headless", value=False)
    with col1:
        if st.button("▶️ Start", disabled=sss.running):
            if task:
                browser_session = BrowserSession(
                    headless=headless,
                    window_size={"width": 800, "height": 600},
                )

                llm = get_llm(llm=LLM_ID)
                sss.agent = Agent(task=task, llm=llm, browser_session=browser_session)
                sss.running = True
                sss.agent_history = None
    with col2:
        if st.button("⏹️ Stop", disabled=not sss.running):
            if sss.agent:
                sss.agent.stop()
            sss.running = False
            sss.agent = None

# Status display
with st.container():
    (status_col,) = st.columns(1)
    with status_col:
        if sss.running:
            st.success("✅ Agent is actively browsing")
            if sss.agent:
                # Run agent and get page content
                try:
                    sss.agent_history = asyncio.run(sss.agent.run())
                except Exception as e:
                    st.error(f"Agent error: {str(e)}")
                sss.running = False
        else:
            st.info("⏸️ Agent is stopped")

# Display content in iframe
if sss.agent_history:
    sss.running = False
    st.write("### result")
    st.write(sss.agent_history.final_result())
