# Telnyx AI Plugin — Workspace Rules

This workspace has all 11 Telnyx plugins installed (32 skill files totaling ~660KB of Telnyx API knowledge).

## Installed Plugin Skills

### `telnyx-messaging` — SMS/MMS
- `telnyx-messaging-hosted-javascript` — Send/receive SMS/MMS with Node.js SDK
- `telnyx-messaging-hosted-python` — Send/receive SMS/MMS with Python SDK

### `telnyx-voice` — Voice API
- `telnyx-voice-javascript` — Call control, inbound/outbound calls (JS)
- `telnyx-voice-python` — Call control, inbound/outbound calls (Python)
- `telnyx-voice-advanced-javascript` — AMD, noise suppression, deepfake detection (JS)
- `telnyx-voice-advanced-python` — AMD, noise suppression, deepfake detection (Python)
- `telnyx-voice-streaming-javascript` — Media streaming, WebSockets (JS)
- `telnyx-voice-streaming-python` — Media streaming, WebSockets (Python)
- `telnyx-voice-conferencing-javascript` — Conferences, SIPREC, recording (JS)
- `telnyx-voice-conferencing-python` — Conferences, SIPREC, recording (Python)

### `telnyx-whatsapp` — WhatsApp Business API
- `telnyx-whatsapp-javascript` — WhatsApp messages & templates (JS)
- `telnyx-whatsapp-python` — WhatsApp messages & templates (Python)

### `telnyx-email` — Email API
- `telnyx-email-curl` — Transactional email send
- `telnyx-email-domains-curl` — Sending domains management

### `telnyx-tts` — Text-to-Speech
- `telnyx-tts-python` — TTS via Telnyx and third-party voices

### `telnyx-stt` — Speech-to-Text
- `telnyx-stt-python` — STT transcription (OpenAI-compatible)

### `telnyx-verify` — Phone Verification / 2FA
- `telnyx-verify-javascript` — OTP via SMS/call/flash (JS)
- `telnyx-verify-python` — OTP via SMS/call/flash (Python)

### `telnyx-numbers` — Number Management
- `telnyx-numbers-javascript` — Search, buy, manage numbers (JS)
- `telnyx-numbers-python` — Search, buy, manage numbers (Python)

### `telnyx-webrtc` — WebRTC
- `telnyx-webrtc-javascript` — WebRTC API (JS)
- `telnyx-webrtc-client-js` — Browser WebRTC client SDK

### `telnyx-ai` — AI Inference, Assistants & Meeting Bot
- `telnyx-ai-assistants-javascript` — AI assistants (JS)
- `telnyx-ai-assistants-python` — AI assistants (Python)
- `telnyx-ai-inference-javascript` — AI inference (JS)
- `telnyx-ai-inference-python` — AI inference (Python)
- `telnyx-ai-outbound-voice-python` — Outbound voice AI agent (Python)
- `telnyx-meeting-bot` — Meeting Bot for recording/transcription

### `telnyx-platform` — Account, SIP, TeXML, OAuth
- `telnyx-sip-javascript` — SIP connections & trunks (JS)
- `telnyx-sip-python` — SIP connections & trunks (Python)
- `telnyx-texml-javascript` — TeXML call control (JS)
- `telnyx-oauth-javascript` — OAuth management (JS)

## Key API Details

- **Base URL**: `https://api.telnyx.com/v2`
- **Auth**: `Authorization: Bearer YOUR_TELNYX_API_KEY`
- **MCP Server**: `https://api.telnyx.com/v2/mcp` (add to `.cursor/mcp.json` or equivalent)
- **Docs**: https://developers.telnyx.com
- **SDK (Node.js)**: `npm install telnyx`
- **SDK (Python)**: `pip install telnyx`

## Coding Guidelines

When writing Telnyx code for this project:
1. Always use the official SDK (`telnyx` npm package or `telnyx` PyPI package) rather than raw HTTP calls unless skills specify curl
2. Handle webhooks properly — Telnyx sends webhook events for async call/messaging events
3. Use environment variables for API keys (`TELNYX_API_KEY`)
4. For voice: set up a call control application and webhook URL before making calls
5. For messaging: configure a messaging profile before sending SMS/MMS
