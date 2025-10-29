Project Overview

Flank is a conversational backend system that integrates Meta WhatsApp Webhooks, Redis caching, and MongoDB to manage user interactions and store contextual conversation summaries. It’s designed for scalability, fast message delivery, and persistent memory for user sessions.
The backend is built with Python (FlaskAPI) and deployed on Vercel Cloud.

Release Notes

Version: 1.0.0
Release Date: October 2025

Highlights:

Initial stable release of the Flank backend service.
Integrated WhatsApp webhook for message delivery and verification.
Added Redis caching layer for active conversations.
MongoDB used for metadata and chat summaries.
Cloud deployment on Vercel for high availability.

Architecture Overview

Core Components:

Flask – RESTful backend framework.
WhatsApp Cloud API – Handles message events via Meta Webhook.
Redis – Stores active session and conversation cache.
MongoDB – Stores user metadata and long-term summaries.
OpenAI API – Processes messages and generates intelligent responses.

Installation Instructions
1. Clone the repository
git clone https://github.com/Flank-Digital/flank-be
cd flank-be

2. Create and configure .env file
VERIFY_TOKEN=<your_meta_verify_token>
APP_SECRET=<your_meta_app_secret>
PHONE_NUMBER_ID=<your_phone_number_id>
WHATSAPP_TOKEN=<your_whatsapp_access_token>

OPENAI_API_KEY=<your_openai_api_key>

REDIS_HOST=<your_redis_host>
REDIS_PORT=<your_redis_port>
REDIS_PASSWORD=<your_redis_password>
REDIS_DECODE_RESPONSES=true

MONGODB_URI=<your_mongodb_connection_string>
MONGODB_DB=Flank
PORT=3001

3. Install dependencies
pip install -r requirements.txt

4. Run the application
python main.py

By default, the app will run on http://localhost:3001

Running Instructions

Start your local Redis and MongoDB instances (or ensure remote access).
Launch the Flask backend using python main.py.

Expose your local server using Ngrok for public access:
ngrok http 3001
Register the Ngrok public URL as the Webhook URL in your Meta Developer Console.

Credential Information

To deploy or run the backend, you must configure the following environment variables:

VERIFY_TOKEN  Token used for webhook verification with Meta
APP_SECRET  App secret from Meta Developer Console
PHONE_NUMBER_ID  WhatsApp business phone number ID
WHATSAPP_TOKEN  Access token for sending and receiving WhatsApp messages
OPENAI_API_KEY  API key for OpenAI model processing
REDIS_HOST / REDIS_PORT / REDIS_PASSWORD  Redis Cloud configuration
MONGODB_URI  MongoDB Atlas connection string
MONGODB_DB  MongoDB database name

API Endpoints
Method	Endpoint	        Description
GET	    /webhook/whatsapp	Verifies webhook setup with Meta
POST	/webhook/whatsapp	Receives and processes incoming WhatsApp messages

Future Enhancements
Prompt content related history text in prompting LLM.
Adapt the stages automatically based on user message.
Implement retry and failover mechanism for message delivery.
Enable multi-user conversation routing via Redis pub/sub.
Building a meta account for the Flank application.