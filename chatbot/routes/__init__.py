"""Titik masuk pendaftaran semua route ke Flask app."""
from chatbot.routes import admin, auth, public


def register_routes(app):
    public.register(app)
    auth.register(app)
    admin.register(app)
