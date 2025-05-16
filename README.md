# BardKeeper

A CLI tool for managing rsync-based archive operations between remote servers and local machines.

DISCLAIMER : I used CLaude to generate this so this is not tested that well and would need additional work. Use at your own risks.

## Features

- **Simple rsync management**: Use rsync to securely copy files from remote servers to local directories
- **Compression support**: Optionally compress synced directories with configurable compression commands
- **Job tracking**: Keep track of when jobs were last synced and their status
- **Directory tree visualization**: View directory structures without having to navigate to them
- **Automated scheduling**: Set up cron-like schedules for automatic syncing
- **Progress tracking**: Monitor rsync progress during transfers
- **Nice UI**: Rich tables, emojis, and menus for a pleasant terminal experience

## Installation

```bash
pip install bardkeeper
```

For scheduling support:
```bash
pip install bardkeeper[schedule]
```

## Requirements

- Python 3.7+
- rsync installed on your system
- SSH access to remote servers

## Usage

### Adding a new sync job

```bash
bardkeeper add
```

This will prompt you for details like the remote server address, username, paths, and compression options. You can also provide these as command-line options:

```bash
bardkeeper add --name "my-server-backup" --host "server.example.com" \
    --username "user" --remote-path "/var/www/html" \
    --local-path "~/backups/server-www" --use-compression
```

### Listing all sync jobs

```bash
bardkeeper list
```

This shows a table with all configured sync jobs and their status.

### Syncing a job

```bash
bardkeeper sync my-server-backup
```

Without arguments, you'll get a menu to select which job to sync:

```bash
bardkeeper sync
```

### Getting detailed information about a job

```bash
bardkeeper info my-server-backup
```

This shows details including a directory tree of the synced files.

### Managing a job's settings

```bash
bardkeeper manage my-server-backup
```

This allows you to change settings like the remote server, paths, compression, etc.

### Configuration

```bash
bardkeeper config
```

Manage global settings like database location, compression commands, and cache options.

### Removing a job

```bash
bardkeeper remove my-server-backup
```

Add `--remove-files` to also delete the synced files.

## Automation

BardKeeper supports automated syncing through the `--cron-schedule` option when adding or managing jobs. For example:

```bash
# Daily at 3 AM
bardkeeper add --name "daily-backup" --cron-schedule "0 3 * * *" ...
```

You can then run BardKeeper regularly (e.g., via system cron or a service) with:

```bash
bardkeeper sync
```

It will automatically sync all jobs that are due to run according to their schedule.

## License

MIT License
