from django.conf import settings
from rest_framework import serializers

from .models import KnowledgeDocument

ALLOWED_TYPES = {"text/plain", "text/markdown", "text/html"}


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeDocument
        fields = ["id", "title", "file", "status", "error", "chunk_count", "created_at"]
        read_only_fields = ["id", "status", "error", "chunk_count", "created_at"]

    def validate_file(self, upload):
        if upload.size > settings.KNOWLEDGE_MAX_FILE_BYTES:
            raise serializers.ValidationError("File is too large.")
        if upload.content_type not in ALLOWED_TYPES:
            raise serializers.ValidationError("Only text, Markdown and HTML files are supported.")
        return upload


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000, trim_whitespace=True)


class CitationSerializer(serializers.Serializer):
    source_id = serializers.CharField()
    doc_id = serializers.CharField()
    title = serializers.CharField()
    section = serializers.CharField(allow_blank=True)
    quote = serializers.CharField()
    start = serializers.IntegerField(allow_null=True)
    end = serializers.IntegerField(allow_null=True)


class AnswerSerializer(serializers.Serializer):
    answer = serializers.CharField()
    found = serializers.BooleanField()
    citations = CitationSerializer(many=True)
