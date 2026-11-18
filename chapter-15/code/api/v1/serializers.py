class DocumentSerializer(serializers.ModelSerializer):
    ...
    class Meta:
        model = Document
        fields = ["id", "filename", "status", "chunk_count", "error",
                  "created_at"]
        read_only_fields = ["status", "chunk_count", "error", "created_at"]
