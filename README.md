# OpenAI Batch Processing with Rate Limiting

A Streamlit application for running and monitoring batch requests to OpenAI APIs with configurable rate limiting.

## Overview

This application demonstrates how to efficiently process multiple AI requests while respecting rate limits imposed by OpenAI services. It visualizes metrics in real-time including TPM (Tokens Per Minute), RPM (Requests Per Minute), and other performance indicators.

## Features

- **Configurable Concurrency**: Run multiple simultaneous requests with adjustable executor count
- **Rate Limiting**: Configure both RPM (Requests Per Minute) and TPM (Tokens Per Minute) limits
- **Real-time Metrics**: Monitor performance with live charts and statistics
- **Error Handling**: Automatically requeue failed requests when rate limits are hit
- **Model Selection**: Support for multiple OpenAI model configurations through environment variables

## Setup

### Prerequisites

- Python 3.8+
- An Azure OpenAI account with API access

### Installation

1. Clone this repository:
   ```
   git clone <repository-url>
   cd oai-batch-rate
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Configure your `.env` file with your OpenAI API credentials:
   ```
   MODEL_GPT4O_1="GPT-4o 1kTPM 6RPM"
   DEPLOYMENT_NAME_GPT4O_1=your-deployment-name
   ENDPOINT_GPT4O_1=your-endpoint-url
   API_KEY_GPT4O_1=your-api-key
   API_TYPE_GPT4O_1=openai
   API_VERSION_GPT4O_1=2024-10-21
   ```
   
   You can add multiple model configurations by creating additional sets with different suffixes.

## Usage

1. Start the Streamlit application:
   ```
   streamlit run app.py
   ```
