# app/main.py
import streamlit as st

from .mail_rules import fetch_and_classify
from .mail_client import get_inbox_emails


def main():
    st.set_page_config(page_title="Mac Mail Sorter", page_icon="📬")
    st.title("Mac Mail Sorter (Ollama-powered)")

    st.write(
        "This tool runs on your Mac Mini, reads Inbox messages from Apple Mail, "
        "asks a local Ollama model how to classify them, and moves them into folders."
    )

    st.sidebar.header("Options")
    limit = st.sidebar.slider("Max emails to process", min_value=5, max_value=100, value=20, step=5)

    if st.button("Preview Inbox Emails"):
        with st.spinner("Fetching emails from Apple Mail..."):
            emails = get_inbox_emails(limit=limit)
        if not emails:
            st.info("No emails found or Apple Mail returned nothing.")
        else:
            st.subheader("Inbox preview")
            for e in emails:
                st.markdown(
                    f"**ID:** `{e['id']}`  \n"
                    f"**From:** {e['sender']}  \n"
                    f"**Subject:** {e['subject']}  \n"
                    f"**Preview:** {e['preview'][:300]}"
                )
                st.markdown("---")

    if st.button("Process Inbox with Ollama"):
        with st.spinner("Classifying and moving emails..."):
            result = fetch_and_classify(limit=limit)

        decisions = result.get("decisions", {})
        errors = result.get("errors", {})

        if decisions:
            st.subheader("Decisions")
            for eid, folder in decisions.items():
                st.write(f"- Email `{eid}` → **{folder}**")
        else:
            st.info("No decisions returned (maybe no emails or Ollama error).")

        if errors:
            st.subheader("Errors")
            for key, err in errors.items():
                st.error(f"{key}: {err}")


if __name__ == "__main__":
    main()
