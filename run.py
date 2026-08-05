"""Entry point buat jalanin aplikasi: `python run.py`."""
from chatbot import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
