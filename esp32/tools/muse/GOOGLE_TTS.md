# Google Cloud Text-to-Speech (optional)

Voice-note replies can be read by Google Cloud, directly from the ESP32.
No always-on PC or phone is needed. Recording and the BOOT toggle are unchanged.
This uses reply text, not the Muse app's VoiceBox audio attachments.

Enable the Cloud Text-to-Speech API in a billing-enabled Google Cloud project.
Create an API key restricted to that API (`texttospeech.googleapis.com`).
Use a private, ignored build-directory `sdkconfig`:

```ini
CONFIG_MUSE_GOOGLE_TTS=y
CONFIG_MUSE_GOOGLE_TTS_API_KEY="YOUR_PRIVATE_KEY"
CONFIG_MUSE_GOOGLE_TTS_LANGUAGE="ja-JP"
CONFIG_MUSE_GOOGLE_TTS_VOICE="ja-JP-Wavenet-B"
```

The feature defaults off and requires the full PSRAM chat buffers, not the
compact 2 MB profile. Do not commit keys, configured sdkconfigs, build artifacts
or firmware binaries containing a key. Google AI Studio keys are a different
service. Cloud billing and API quotas apply; consult Google's current pricing.

Each completed voice-note reply (up to the existing 1023-byte caption limit)
is synthesized once as 16 kHz MP3 and decoded by the existing audio pipeline.
Typed serial chat and unrelated app messages are not synthesized. Speaker off
or volume zero skips synthesis. Network, quota and decoding errors keep the
reply visible at reading pace. There are no automatic paid retries.

HTTPS checks Google's certificate and hostname, with redirects disabled. Enabling
this feature selects ESP-IDF's cross-signed certificate bundle verification
(required for Google's cross-signed GTS root chain), retaining CA validation. The
worker has a 45-second operation deadline (individual blocking network calls
can take up to 15 seconds), a 512 KiB decoded MP3 limit and bounded response
storage. Peak extra PSRAM is approximately 1.4 MiB while parsing the response.
Cancelled workers own their text and buffers until they finish; they cannot
write into another turn. Cancelled requests already accepted by Google can
still count toward usage. Keys and response bodies are never logged.

## Hardware verification

From an idle device, send `>tts.test` followed by a newline over the serial
console (115200 baud). This makes one Google request and plays a fixed Japanese
sentence through the normal idle-only audio test path. It does not contact Muse
or change pairing, Wi-Fi, volume or sleep settings. Logs report HTTP/transport
failure or the MP3 byte count, then the decoded sample count.

Then press BOOT once, speak, and press BOOT again to send. The reply should
appear as captions and play through the speaker. Starting another voice note
cancels the previous reply. Muting the speaker retains text-only replies.

References:
- https://docs.cloud.google.com/text-to-speech/docs/create-audio
- https://docs.cloud.google.com/docs/authentication/api-keys
- https://cloud.google.com/text-to-speech/pricing

## Change the voice over USB

Open `serial_setup.html` in Chrome, connect the device, choose **Sound →
Text-to-speech voice**, then **Save changes**. Japanese WaveNet A/B are female;
C/D are male. The UI defaults to English and can switch to Japanese.
The device saves the choice in NVS and uses it for the next synthesis, including
`>tts.test`, without restarting. An already running utterance keeps its voice.
Reconnecting or rebooting reads back the saved value. The default before any
choice is the build's `CONFIG_MUSE_GOOGLE_TTS_VOICE`.

The equivalent UART command is `>tts_voice=ja-JP-Wavenet-D`. `>status` reports
`tts.enabled`, `tts.language` and `tts.voice`. Only firmware with this capability
and Japanese TTS enables the selector; existing non-TTS firmware retains all
other settings. Invalid names and failed NVS writes are rejected.
