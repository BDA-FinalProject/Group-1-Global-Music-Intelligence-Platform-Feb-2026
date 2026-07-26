"""Serializers for the chatbot API."""
from rest_framework import serializers


class ChatMessageRequestSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000)


class ChatMessageResponseSerializer(serializers.Serializer):
    reply = serializers.CharField()
    sources = serializers.ListField(child=serializers.CharField(), required=False)
