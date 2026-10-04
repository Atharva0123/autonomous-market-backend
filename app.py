import uvicorn
import gradio as gr
from api.main import app

# Create a simple Gradio interface just to satisfy Hugging Face's SDK requirement
def health_check():
    return "Autonomous Market Trend API is running perfectly!"

demo = gr.Interface(
    fn=health_check, 
    inputs=None, 
    outputs="text",
    title="Market Intelligence API",
    description="This is the backend API. The main frontend is hosted on Vercel."
)

# Mount the FastAPI app inside the Gradio app so both are served
# HuggingFace expects the app to be served on 0.0.0.0:7860
app = gr.mount_gradio_app(app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
