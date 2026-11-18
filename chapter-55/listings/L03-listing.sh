# on your own computer
age-keygen -o ai-chat-backup.key        # keep this file in your password manager
 
# on the server (age and rclone come from the OS package manager)
sudo apt install age rclone
export BACKUP_AGE_RECIPIENT=age1...     # the PUBLIC key printed above
export BACKUP_HEARTBEAT_URL=https://hc-ping.com/your-uuid-for-backups
python3 ops/backup.py
ls -l backups/
