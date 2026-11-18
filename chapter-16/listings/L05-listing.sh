python3 -c "
import quopri
print(quopri.decodestring(open('server.log', 'rb').read()).decode())" | less
 example output (text part)
Hi Ada,

Please confirm your email address to finish setting up your account:

http://localhost:3000/verify-email?token=eyJ1aWQiOjEsImVtYWlsIjoiYWRhQGV4YW1wbGUuY29tIn0:1xNoEd:9BYiRz...

The link expires in 2 days.
