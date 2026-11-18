printf '%%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%%%EOF\n' > report.pdf
printf 'MZ\000\220\000 this is not a pdf' > fake.pdf
printf 'just some notes\n' > notes.txt

curl -s -X POST localhost:8000/api/v1/documents -H "$A" -F file=@report.pdf
curl -s -X POST localhost:8000/api/v1/documents -H "$A" -F file=@report.pdf     # again
curl -s -w ' [%{http_code}]\n' -X POST localhost:8000/api/v1/documents -H "$A" -F file=@fake.pdf
curl -s -X POST localhost:8000/api/v1/documents -H "$A" -F file=@notes.txt
 example output
{"id":"942c5fc3-f4c7-4cd6-ba70-045b1e64d412","filename":"report.pdf","content_type":"application/pdf",
 "size_bytes":51,"status":"uploaded","error":"","created_at":"2026-11-02T09:21:48.693610Z"}

(the same document again, with status 200 instead of 202: nothing was stored twice)

{"error":{"code":"unsupported_file_type","message":"This type of file is not accepted.","request_id":"req_6bb83b"}} [415]

{"id":"f06e2e0b-caf6-4cf6-aa7c-12b098e33f39","filename":"notes.txt","content_type":"text/plain","size_bytes":16,...}
