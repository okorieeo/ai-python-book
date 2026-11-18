# ------------------------------------------------------------ admin panel
class AdminUserSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="public_id", read_only=True)
    conversation_count = serializers.IntegerField(read_only=True)
    tokens_30d = serializers.IntegerField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "is_active", "date_joined",
                  "last_login", "conversation_count", "tokens_30d"]
        read_only_fields = fields

class OverviewSerializer(serializers.Serializer):
    users_total = serializers.IntegerField()
    users_new_7d = serializers.IntegerField()
    tokens_today = serializers.IntegerField()
    messages_today = serializers.IntegerField()
    documents_total = serializers.IntegerField()

class UsagePointSerializer(serializers.Serializer):
    date = serializers.DateField()
    input_tokens = serializers.IntegerField()
    output_tokens = serializers.IntegerField()
    calls = serializers.IntegerField()

class UsageSeriesSerializer(serializers.Serializer):
    days = serializers.IntegerField()
    series = UsagePointSerializer(many=True)

class TopUserSerializer(serializers.Serializer):
    username = serializers.CharField()
    tokens = serializers.IntegerField()

class StatusCountSerializer(serializers.Serializer):
    status = serializers.CharField()
    count = serializers.IntegerField()
