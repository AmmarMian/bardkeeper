# BardKeeper Compression Guide

This guide explains how compression works in BardKeeper and how to use it effectively.

## How Paths Work in BardKeeper

BardKeeper intelligently handles paths to make syncing and compression more intuitive:

1. **Remote path structure is preserved**: When you specify a remote path like `/remote/server/data`, BardKeeper automatically creates a `data` subdirectory in your local path.

2. **Example path handling**:
   - Remote path: `/home/user/project`
   - Local path: `/backups`
   - Actual sync destination: `/backups/project/`

3. **Compression uses the subdirectory name**:
   - Files are synced to `/backups/project/`
   - Archive is created as `/backups/project.tar.gz`
   - The `/backups/project/` directory is removed

This approach ensures that:
- Your original directory structure is maintained
- Multiple backups from different sources don't conflict
- Archive names are meaningful and related to their content

## Path Recommendations

When using compression, consider these path recommendations:

1. **Use meaningful directory names**: Since the compressed archive will use the directory name as its base name, choose descriptive directory names.

   Good: `/backups/project-files`
   Result: `/backups/project-files.tar.gz`

2. **Avoid trailing slashes** in your local path when using compression, as they can cause confusion with basename extraction.

3. **Use parent directories** to organize multiple archives:
   ```
   /backups/
   ├── project1.tar.gz
   ├── project2.tar.gz
   └── project3.tar.gz
   ```

## Commands for Working with Compressed Archives

### Viewing the contents

To view the contents of a compressed job:

```bash
bardkeeper info my-compressed-job
```

This will display information about the job and a preview of the archive contents.

### Extracting an archive

BardKeeper doesn't provide a direct command to extract archives, but you can use standard Linux commands:

```bash
# Extract an archive
tar -xzf /path/to/archive.tar.gz -C /extraction/directory
```

## Toggling Compression

You can enable or disable compression for an existing job:

```bash
bardkeeper manage my-job-name
```

Then select "Toggle Compression" from the menu.

When changing from uncompressed to compressed:
- The existing directory will be compressed
- The original directory will be removed

When changing from compressed to uncompressed:
- The archive will be extracted
- The archive file will be removed
