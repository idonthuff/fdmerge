## The purpose of this tool is to merge multiple folders of files down into a single target folder and remove ALL duplicates, no matter where the files are.

There are lots of file merge/dedupe tools already. So what makes this one different?
- Any number of source folders can be merged at the same time
- Files are identified ONLY by their contents.  Filenames, sizes, dates, and paths are IGNORED and IRRELEVANT
- Duplicates are removed **NO MATTER WHERE** they exist in the source folders.  Only 1 file with each unique content (by SHA-256 hash) will be copied to the target

Why should you use it?  You probably shouldn't, unless you care more about the contents of files than where they are sitting.

### Common usage scenarios might be:
~~~
Photos1
  2022
    file1.jpg
    file1_copy.jpg
    file2.jpg
  2023
    file3.jpg
    file4.jpg
  2024
    file5.jpg  
~~~
~~~
Photos2
  2022
    file1.jpg
    file2.jpg
    file8.jpg
  2023
    Project1
      file9.jpg
    file1_copy_2.jpg
  2024
    file5.jpg
  2025
    file6.jpg
    file7.jpg
~~~
~~~
Photos3
  2021
    file10.jpg
  2022
    file1.jpg
    file2.jpg
    file11.jpg
~~~


## Critical Note:
:warning: **The unique file that is found FIRST is the one that will be copied to the target.**<br>
If that happens to be **Photos2/2023/file1_copy_2.jpg** instead of **Photos1/2022/file1.jpg**, then so be it!<br><br>
:bulb: Source folders are scanned in the order they are provided on the command line, so place the highest-priority source folder first!<br>
Finding files within each source folder produces non-deterministic ordering, using Python's os.scandir() function.

## TARGET
~~~
  2021
    file10.jpg
  2022
    file1.jpg
    ---------------> file1_copy.jpg     **EXCLUDED**
    file2.jpg
    file8.jpg
    file11.jpg
  2023
    file3.jpg
    file4.jpg
    Project1
      file9.jpg
    ---------------> file1_copy_2.jpg     **EXCLUDED**
  2024
    file5.jpg
  2025
    file6.jpg
    file7.jpg
~~~

**This will probably take longer to run than other merge tools because a full SHA-256 hash of every file is calculated twice.**<br>
:memo: One hash operation to identify unique files, and one operation as a read-after-write verification of the copy.

## Usage
usage: fdmerge.py [-h] [-V] [--debug] [--human-readable] [--display-collisions] [--display-renames] [--dry-run] {merge-sources} ...

Merge all specified directories into a single target folder and dedup based on file contents (SHA256 hash)
~~~
options:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
  --debug               Include this switch to produce debug output
  --human-readable      Include this switch to indent log output to make it easier to read interactively
  --display-collisions  Include this switch to show hash collisions at the end of the run
  --display-renames     Include this switch to show renamed files at the end of the run
  --dry-run             Include this switch to do all processing but skip actually copying files

positional arguments:
  {merge-sources}
  usage: fdmerge.py merge-sources [-h] --folders FOLDERS [FOLDERS ...] --target TARGET [--exclude-extensions EXCLUDE_EXTENSIONS [EXCLUDE_EXTENSIONS ...]]

  -h, --help            show this help message and exit
  --folders FOLDERS [FOLDERS ...]
                        Paths to source folders to be recursively checked and merged
  --target TARGET       Target folder
  --exclude-extensions EXCLUDE_EXTENSIONS [EXCLUDE_EXTENSIONS ...]
                        File extensions to exclude from selection
~~~
