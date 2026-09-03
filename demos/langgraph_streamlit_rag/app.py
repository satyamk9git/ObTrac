"""
Legacy entrypoint — delegates to streamlit_main_app.py.
Kept so that old background task commands (streamlit run demos/langgraph_streamlit_rag/app.py) still work.
"""
import os

_target = os.path.join(os.path.dirname(__file__), "streamlit_main_app.py")
exec(compile(open(_target).read(), _target, "exec"))
