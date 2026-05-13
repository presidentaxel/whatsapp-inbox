-- Transcription automatique des messages audio/voice (Gemini), texte affiché dans l'UI

ALTER TABLE messages
ADD COLUMN IF NOT EXISTS audio_transcript TEXT;

COMMENT ON COLUMN messages.audio_transcript IS
  'Transcription du média audio/voice (inbound), produite côté backend via Gemini';
