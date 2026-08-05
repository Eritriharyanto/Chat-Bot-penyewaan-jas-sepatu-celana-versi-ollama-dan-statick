"""Layer service: logic bisnis chatbot, dipisah dari route Flask supaya
gampang di-test & dibaca. Semua modul di sini stateless terhadap request
HTTP -- data mutable (KB, INTENTS, dll) selalu diakses lewat `chatbot.state`."""
