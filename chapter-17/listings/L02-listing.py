# DANGEROUS: exposes password, is_staff, is_superuser... and accepts writes
class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"

# SAFE: an explicit allow-list; identity fields cannot be changed through this endpoint
class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["public_id", "email", "first_name", "last_name"]
        read_only_fields = ["public_id", "email"]
