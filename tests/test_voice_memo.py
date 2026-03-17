"""Tests für Voice-Memo Feature (Telegram → Gemini Audio)."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


class TestHandleUpdateVoice:
    """Tests für Voice-Message-Erkennung in handle_update."""

    @pytest.mark.asyncio
    async def test_voice_message_routes_to_handler(self):
        """Voice-Nachricht wird an _handle_voice_memo weitergeleitet."""
        update = {
            "message": {
                "chat": {"id": "12345"},
                "voice": {
                    "file_id": "test_file_id",
                    "duration": 5,
                    "file_size": 10000,
                },
            }
        }

        with patch("services.telegram_bot.settings") as mock_settings, \
             patch("services.telegram_bot._handle_voice_memo", new_callable=AsyncMock) as mock_voice:
            mock_settings.TELEGRAM_CHAT_ID = "12345"

            from services.telegram_bot import handle_update
            await handle_update(update)

            mock_voice.assert_called_once_with(
                "12345",
                update["message"]["voice"],
                "",
            )

    @pytest.mark.asyncio
    async def test_text_message_still_works(self):
        """Text-Commands funktionieren weiterhin (Regression)."""
        update = {
            "message": {
                "chat": {"id": "12345"},
                "text": "/help",
            }
        }

        with patch("services.telegram_bot.settings") as mock_settings, \
             patch("services.telegram_bot._cmd_help", new_callable=AsyncMock) as mock_help:
            mock_settings.TELEGRAM_CHAT_ID = "12345"

            from services.telegram_bot import handle_update
            await handle_update(update)

            mock_help.assert_called_once_with("12345")

    @pytest.mark.asyncio
    async def test_voice_with_caption(self):
        """Voice-Nachricht mit Caption wird korrekt weitergeleitet."""
        update = {
            "message": {
                "chat": {"id": "12345"},
                "voice": {
                    "file_id": "abc123",
                    "duration": 10,
                    "file_size": 5000,
                },
                "caption": "Schau dir mal NVDA an",
            }
        }

        with patch("services.telegram_bot.settings") as mock_settings, \
             patch("services.telegram_bot._handle_voice_memo", new_callable=AsyncMock) as mock_voice:
            mock_settings.TELEGRAM_CHAT_ID = "12345"

            from services.telegram_bot import handle_update
            await handle_update(update)

            mock_voice.assert_called_once_with(
                "12345",
                update["message"]["voice"],
                "Schau dir mal NVDA an",
            )

    @pytest.mark.asyncio
    async def test_no_chat_id_ignored(self):
        """Update ohne Chat-ID wird ignoriert."""
        update = {"message": {"text": "hello"}}

        with patch("services.telegram_bot.settings") as mock_settings:
            mock_settings.TELEGRAM_CHAT_ID = "12345"

            from services.telegram_bot import handle_update
            # Should not raise
            await handle_update(update)

    @pytest.mark.asyncio
    async def test_wrong_chat_id_rejected(self):
        """Updates von fremden Chat-IDs werden abgelehnt."""
        update = {
            "message": {
                "chat": {"id": "99999"},
                "voice": {"file_id": "x", "duration": 1, "file_size": 100},
            }
        }

        with patch("services.telegram_bot.settings") as mock_settings, \
             patch("services.telegram_bot._handle_voice_memo", new_callable=AsyncMock) as mock_voice:
            mock_settings.TELEGRAM_CHAT_ID = "12345"

            from services.telegram_bot import handle_update
            await handle_update(update)

            mock_voice.assert_not_called()


class TestHandleVoiceMemo:
    """Tests für _handle_voice_memo Funktion."""

    @pytest.mark.asyncio
    async def test_no_gemini_sends_error(self):
        """Ohne Gemini-Config wird Fehlermeldung gesendet."""
        mock_send = AsyncMock()

        with patch("services.telegram_bot.settings") as mock_settings, \
             patch("services.telegram.send_message", mock_send), \
             patch("services.telegram.settings") as mock_tg_settings:
            mock_settings.gemini_configured = False
            mock_tg_settings.TELEGRAM_BOT_TOKEN = "test"
            mock_tg_settings.TELEGRAM_CHAT_ID = "123"

            from services.telegram_bot import _handle_voice_memo
            await _handle_voice_memo("123", {"file_id": "x", "duration": 1, "file_size": 100})

            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][0]
            assert "Gemini" in sent_text

    @pytest.mark.asyncio
    async def test_file_too_large(self):
        """Zu große Audio-Datei wird abgelehnt."""
        voice = {
            "file_id": "x",
            "duration": 300,
            "file_size": 25 * 1024 * 1024,  # 25 MB
        }
        mock_send = AsyncMock()

        with patch("services.telegram_bot.settings") as mock_settings, \
             patch("services.telegram.send_message", mock_send), \
             patch("services.telegram.settings") as mock_tg_settings:
            mock_settings.gemini_configured = True
            mock_tg_settings.TELEGRAM_BOT_TOKEN = "test"
            mock_tg_settings.TELEGRAM_CHAT_ID = "123"

            from services.telegram_bot import _handle_voice_memo
            await _handle_voice_memo("123", voice)

            # Sollte 2 Nachrichten senden: "Empfangen" und "zu groß"
            assert mock_send.call_count >= 1
            all_texts = " ".join(c[0][0] for c in mock_send.call_args_list)
            assert "groß" in all_texts


class TestDownloadTelegramFile:
    """Tests für download_telegram_file in telegram.py."""

    @pytest.mark.asyncio
    async def test_download_success(self):
        """Erfolgreicher File-Download über Telegram API."""
        mock_get_file_resp = MagicMock()
        mock_get_file_resp.status_code = 200
        mock_get_file_resp.json.return_value = {
            "ok": True,
            "result": {"file_path": "voice/file_123.ogg"},
        }

        mock_file_resp = MagicMock()
        mock_file_resp.status_code = 200
        mock_file_resp.content = b"fake_audio_data"

        with patch("services.telegram.settings") as mock_settings, \
             patch("services.telegram.httpx.AsyncClient") as mock_client_cls:
            mock_settings.TELEGRAM_BOT_TOKEN = "test_token"

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=[mock_get_file_resp, mock_file_resp])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            from services.telegram import download_telegram_file
            result = await download_telegram_file("test_file_id")

            assert result == b"fake_audio_data"
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_download_no_token(self):
        """Ohne Bot-Token wird RuntimeError geworfen."""
        with patch("services.telegram.settings") as mock_settings:
            mock_settings.TELEGRAM_BOT_TOKEN = ""

            from services.telegram import download_telegram_file
            with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
                await download_telegram_file("test_id")

    @pytest.mark.asyncio
    async def test_download_api_error(self):
        """API-Fehler bei getFile wird als RuntimeError geworfen."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400

        with patch("services.telegram.settings") as mock_settings, \
             patch("services.telegram.httpx.AsyncClient") as mock_client_cls:
            mock_settings.TELEGRAM_BOT_TOKEN = "test_token"

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client

            from services.telegram import download_telegram_file
            with pytest.raises(RuntimeError, match="getFile"):
                await download_telegram_file("test_id")
