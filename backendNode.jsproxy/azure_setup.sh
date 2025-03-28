#!/bin/bash

# Login to Azure (will prompt in browser)
az login

# Create Resource Group
az group create --name PaperVideoRG --location eastus

# Create Azure AI Search
az search service create \
  --name paper-video-search \
  --resource-group PaperVideoRG \
  --sku free \
  --partition-count 1 \
  --replica-count 1

# Create Document Intelligence
az cognitiveservices account create \
  --name paper-doc-intel \
  --resource-group PaperVideoRG \
  --kind FormRecognizer \
  --sku F0 \
  --location eastus

# Create Azure OpenAI
az cognitiveservices account create \
  --name paper-video-ai \
  --resource-group PaperVideoRG \
  --kind OpenAI \
  --sku S0 \
  --location eastus

# Deploy OpenAI models
az cognitiveservices account deployment create \
  --name paper-video-ai \
  --resource-group PaperVideoRG \
  --deployment-name text-embeddings \
  --model-name text-embedding-3-large \
  --model-version "1" \
  --model-format OpenAI \
  --scale-settings-scale-type "Standard"

az cognitiveservices account deployment create \
  --name paper-video-ai \
  --resource-group PaperVideoRG \
  --deployment-name gpt-4-32k \
  --model-name gpt-4-32k \
  --model-version "0613" \
  --model-format OpenAI \
  --scale-settings-scale-type "Standard"
