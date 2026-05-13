-- Anciens accusés WhatsApp stockés comme messages visibles : masquer de l’aperçu liste
UPDATE messages
SET is_system = TRUE
WHERE COALESCE(is_system, FALSE) = FALSE
  AND (
    content_text = '[status update]'
    OR LOWER(COALESCE(message_type, '')) = 'status'
  );
