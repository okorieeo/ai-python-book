# documents/views.py (add)
class DocumentLink(APIView):
    """Give the client a signed URL as JSON, instead of redirecting to it.

    A phone's HTTP client follows our 302 and may send our Authorization header to the
    bucket too. S3 refuses a request that carries two kinds of credentials. So the app
    asks for the link, and then opens it by itself, with no headers.
    """

    def get(self, request, public_id):
        doc = generics.get_object_or_404(request.user.documents, public_id=public_id)
        storage = store.get_storage()
        inline = request.query_params.get("inline") == "1" and (
            doc.content_type.startswith("image/") or doc.content_type == "application/pdf"
        )
        if store.is_local(storage):  # development: the file is served from /media/
            url = request.build_absolute_uri(storage.url(doc.storage_key))
            expires = None
        else:  # production: a link that stops working in 5 minutes
            params = {} if inline else {"ResponseContentDisposition": "attachment"}
            url = storage.url(doc.storage_key, parameters=params)
            expires = 300
        return Response(
            {
                "url": url,
                "expires_in": expires,
                "content_type": doc.content_type,
                "filename": doc.filename,
            }
        )
