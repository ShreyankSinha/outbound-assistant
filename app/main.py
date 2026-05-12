from app.config import get_settings
from app.ui.gradio_debug_app import build_demo


def main() -> None:
    settings = get_settings()
    demo = build_demo()
    demo.launch(server_name=settings.gradio_server_host, server_port=settings.gradio_server_port)


if __name__ == "__main__":
    main()
