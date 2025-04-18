# MIT License

# Copyright (c) 2025 Isaac Huff

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


import sys
import os
import argparse
import time
import hashlib
import shutil
import pprint
import pickle
import textwrap
import string
import random

__version__ = '0.4.0'

def setup_argparser():
    parser = argparse.ArgumentParser(description='Merge all specified directories into a single target folder and dedup based on file contents (SHA256 hash)')
    subparsers = parser.add_subparsers()
    folders_parser = subparsers.add_parser('merge-sources')
    folders_parser.add_argument('--folders', type=str, required=False, nargs='+', help='Paths to source folders to be recursively checked and merged')
    folders_parser.add_argument('--target', type=str, required=True, help='Target folder')
    folders_parser.add_argument('--exclude-extensions', type=str, required=False, nargs='+', help='File extensions to exclude from selection')
    folders_parser.add_argument('--compare-only', type=str, required=False, nargs='+', help='Paths to source folders to be recursively checked, but never actually copied')
    setup_folders_parser(folders_parser)
    folders_parser.set_defaults(func=merge_sources)

    parser.add_argument('-V', '--version', action='version', version="%(prog)s ("+__version__+")")
    parser.add_argument('--debug', action='store_true',help='Include this switch to produce debug output')
    parser.add_argument('--human-readable', action='store_true',help='Include this switch to indent log output to make it easier to read interactively')
    parser.add_argument('--display-collisions', action='store_true',help='Include this switch to show hash collisions at the end of the run')
    parser.add_argument('--display-renames', action='store_true',help='Include this switch to show renamed files at the end of the run')
    parser.add_argument('--dry-run', action='store_true',help='Include this switch to do all processing but skip actually copying files')
    parser.add_argument('--store-hashes', action='store_true',help='Include this switch to save the generated hashtable in a file at the root of each source directory specified with --folders or --compare-only')
    parser.add_argument('--load-hashes', action='store_true',help='Include this switch to load previously generated hashtable from a file at the root of each source directory specified.  THIS WILL NOT account for changes to the filesystem since the hashes were saved!')

    return parser

def setup_folders_parser(parser):
    #we don't have anything to do here, so give a polite greeting
    print('Hello!')
    print('Process beginning at {}'.format(time.strftime('%Y-%m-%d %I:%M:%S%p')))

def print_indented(printarg, flag=False):
    #TODO: this function isn't working perfectly as desired, so it has been turned into a passthrough
    print(printarg)

def run_fast_scandir(dir, ext):
    #ext is a list of file extensions to be EXCLUDED from selection
    subfolders, files = [], []

    for f in os.scandir(dir):
        if f.is_dir():
            subfolders.append(f.path)
        if f.is_file():
            if os.path.splitext(f.name)[1].lower() not in ext:
                files.append(os.path.normpath(f.path))

    for dir in list(subfolders):
        sf, f = run_fast_scandir(dir, ext)
        subfolders.extend(sf)
        files.extend(f)
    return subfolders, files

def count_extensions(filelist):
    res = {}
    for i in filelist:
        fname, ftype = os.path.splitext(i)
        if ftype not in res.keys():
                res[ftype] = 1
        else:
                res[ftype] += 1
    
    return res

def calc_hash(file):
    t = time.process_time()
    filehash_value = None

    if os.path.exists(file):
        with open(file, "rb") as a:
            accumulator = hashlib.file_digest(a, "sha256")
        a.close()

    filehash_value = accumulator.hexdigest()
    et = time.process_time() - t

    return filehash_value, et      #hash of file contents, processing time on CPU

def merge_sources(args):
    ftypes = {}         #dictionary of file extensions (histogram) seen in a single source folder
    s = {}              #dictionary of unique files seen in a single source folder
    d = {}              #dictionary of unique files seen across all source folders
    copies = {}         #dictionary of files which were successfully copied into the target folder
    collisions = {}     #dictionary of file content collisions
    renames = []          #list of files renamed during copy to avoid filename collisions

    #make sure the supplied (single) target folder exists
    normalized_target = os.path.realpath(args.target, strict=False)
    if not os.path.isdir(normalized_target):
         print('The target path {} does not exist'.format(normalized_target))
         sys.exit(1)


    #we need to interate the compare-only folders first, because the purpose is to do as little work as possible
    if args.compare_only is not None:
        for source_folder_index, source_folder in enumerate(args.compare_only, start=0):
            files = {}
            ftypes.clear()
            s.clear()
            print('Processing COMPARE-ONLY folder {}/{}  ({})  at {}             File SHA256 CPUtime'.format(source_folder_index+1, len(args.compare_only), source_folder, time.strftime('%Y-%m-%d %I:%M:%S%p')))
            time_start = time.process_time()   #CPU time, not clock time
            
            statefile_path = os.path.join(source_folder,"fdmerge_state.pkl")

            if args.load_hashes and os.path.isfile(statefile_path): #test and find whether this source has saved hashes                
                with open(statefile_path, 'rb') as statefile:
                    s = pickle.load(statefile)
                    for x in s.values(): #since we are in --folders, we want all loaded files to be considered for copying
                         x[1] = source_folder_index
                         x[2] = 0

            else: #we do not want to load state, or it is not available
                #recursively scan this folder and get files
                if not args.exclude_extensions:
                    args.exclude_extensions = []
                unused1, files = run_fast_scandir(source_folder, args.exclude_extensions)   
                print('{} files have been selected'.format(len(files)))
                
                #see how many of each file type we have (just for summary output - does not affect processing)
                ftypes = count_extensions(files)
                print_indented(pprint.pformat(ftypes, width=200, sort_dicts=True), args.human_readable)

                #iterate files and calculate a hash of the contents of each file
                for j, file in enumerate(files, start=1):
                    file_hash, time_hashing = calc_hash(file)
                    if args.debug:
                        print_indented(" ".join([file, file_hash, str(time_hashing)]), args.human_readable)
                        
                    
                    if file_hash not in d.keys() and file_hash not in s.keys():                   #we have not seen this file content before
                        s[file_hash] = [file, source_folder_index, 0]
                    elif file_hash in collisions.keys():            #we have already had a collision with this file content
                        cvalue = []
                        cvalue =  [file, source_folder_index, 0]
                        collisions[file_hash].append(cvalue)
                    else:                                           #this is the first collision with this file content
                        cvalue = []
                        cvalue = [file, source_folder_index, 0]
                        collisions[file_hash] = [cvalue]
                    if j % 500 == 0:                       #500 is arbitrary batch size for progress reporting
                        print('Completed hashing of {} files at {}'.format(j, time.strftime('%Y-%m-%d %I:%M:%S%p')))


            if args.store_hashes:
                with open(statefile_path, 'wb') as statefile:
                    pickle.dump(s, statefile)
            
            d.update(s)

            time_elapsed = time.process_time() - time_start
            print('Hash calculations took {} seconds of CPU (avg {} sec/file) for folder {}'.format(time_elapsed, (round(float(time_elapsed)/float(len(files)+1), 3)), source_folder)) #FIXME: add 1 to avoid possible divide-by-zero
            print('Timestamp: {}'.format(time.strftime('%Y-%m-%d %I:%M:%S%p')))



    #iterate supplied source folder list and compile the list of unique files to act on
    #do this by hashing files and using the hashes as dictionary keys
    if args.folders is not None:
        for source_folder_index, source_folder in enumerate(args.folders, start=0):
            files = {}
            ftypes.clear()
            s.clear()
            print('Processing folder {}/{}  ({})  at {}             File SHA256 CPUtime'.format(source_folder_index+1, len(args.folders), source_folder, time.strftime('%Y-%m-%d %I:%M:%S%p')))
            time_start = time.process_time()   #CPU time, not clock time

            statefile_path = os.path.join(source_folder,"fdmerge_state.pkl")

            if args.load_hashes and os.path.isfile(statefile_path): #test and find whether this source has saved hashes                
                with open(statefile_path, 'rb') as statefile:
                    s = pickle.load(statefile)
                    for x in s.values(): #since we are in --folders, we want all loaded files to be considered for copying
                         x[2] = 1

            else: #we do not want to load state, or it is not available
                #recursively scan this folder and get files
                if not args.exclude_extensions:
                    args.exclude_extensions = []
                unused1, files = run_fast_scandir(source_folder, args.exclude_extensions)   
                print('{} files have been selected'.format(len(files)))
                
                #see how many of each file type we have (just for summary output - does not affect processing)
                ftypes = count_extensions(files)
                print_indented(pprint.pformat(ftypes, width=200, sort_dicts=True), args.human_readable)

                #iterate files and calculate a hash of the contents of each file
                for j, file in enumerate(files, start=1):
                    file_hash, time_hashing = calc_hash(file)
                    if args.debug:
                        print_indented(" ".join([file, file_hash, str(time_hashing)]), args.human_readable)
                        
                    
                    if file_hash not in d.keys() and file_hash not in s.keys():                   #we have not seen this file content before
                        s[file_hash] = [file, source_folder_index, 1]
                    elif file_hash in collisions.keys():            #we have already had a collision with this file content
                        cvalue = []
                        cvalue =  [file, source_folder_index, 1]
                        collisions[file_hash].append(cvalue)
                    else:                                           #this is the first collision with this file content
                        cvalue = []
                        cvalue = [file, source_folder_index, 1]
                        collisions[file_hash] = [cvalue]
                    if j % 500 == 0:                       #500 is arbitrary batch size for progress reporting
                        print('Completed hashing of {} files at {}'.format(j, time.strftime('%Y-%m-%d %I:%M:%S%p')))

            if args.store_hashes:
                with open(statefile_path, 'wb') as statefile:
                    pickle.dump(s, statefile)
            
            d.update(s)

            time_elapsed = time.process_time() - time_start
            print('Hash calculations took {} seconds of CPU (avg {} sec/file) for folder {}'.format(time_elapsed, (round(float(time_elapsed)/float(len(files)+1), 3)), source_folder)) #FIXME: add 1 to avoid possible divide-by-zero
            print('Timestamp: {}'.format(time.strftime('%Y-%m-%d %I:%M:%S%p')))

    #iterate list of unique files and make copies to the target
    print('File copy operations beginning at {}             [Source File, Folder]   -->   Target'.format(time.strftime('%Y-%m-%d %I:%M:%S%p')))
    i = 0
    for source_hash,value in d.items():
        #value[0-2] = [str]file_path, [int]source_folder_index, [bool]do_copy
        i += 1

        if not value[2]:
             continue

        source_file = os.path.normpath(value[0])
        source_relpath = os.path.relpath(source_file, start=os.path.normpath(args.folders[value[1]]))
        target_file = os.path.normpath(os.path.join(normalized_target, source_relpath))
        target_directory, target_filename = os.path.split(target_file)

        #create the folder hierarchy inside the output folder if necessary
        if not os.path.isdir(target_directory):
             os.makedirs(target_directory, exist_ok=False)
        
        #determine the final name of the file to be copied to the output directory
        j = 0
        while True:
            j += 1
            if os.path.isfile(target_file):
                #we need to change the filename and try again
                #append a 4-character random string to the base filename
                fix = ''.join(random.choices(string.ascii_lowercase, k=4))
                x, y = os.path.splitext(target_file)
                target_file = os.path.join(target_directory, ''.join([x, '__COPY', fix, y]))
                renames.append(target_file)
            else:
                #the filename we have constructed is fine. there is no collision in the output directory
                break

            if j >= 6:
                #this shouldn't happen. we have done multiple renames for the same file and it keeps colliding
                 print('There is a problem with the filename fix loop code, or the filesystem is showing unexpected behavior!')
                 sys.exit(2)
            
        if args.debug:
            print_indented('{}   -->   {}'.format(value, target_file), args.human_readable)

        #if we are in dry-run mode, do not actually copy any files (read-only operation!)
        if args.dry_run:
                print('Skipping all file copy operations :  --dry-run selected')
                break       
            
        if not os.path.isfile(target_file):
            # we can copy because there is no filename collision
            #copy and calculate the hash of the output so that it can be compared with the hash of the source file
            output_file = shutil.copy2(source_file, target_file, follow_symlinks=False)
            output_file_hash, unused2 = calc_hash(output_file)
        
            #keep track of successfully copied files.  BOMB if a perfect copy of any file cannot be made!
            if output_file_hash == source_hash:
                copies[output_file_hash] = target_file
            else:
                 print("File Copy Error!")
                 sys.exit(3)

        if i % 500 == 0: 
            print('Completed copying of {} files at {}'.format(i, time.strftime('%Y-%m-%d %I:%M:%S%p'))) #FIXME: this is not correct when some sources are --compare-only
    
    print('Completed file copy operations at {}'.format(time.strftime('%Y-%m-%d %I:%M:%S%p')))
        
    #show the list of file content collisions if the user wants it
    if args.display_collisions:
         print('The following files had hash collisions and were treated as being identical:')
         print_indented(pprint.pformat(collisions, width=200, sort_dicts=True), args.human_readable)

    if args.display_renames:
         print('The following files were saved with new names to avoid overwriting a different (content) file already in the target location:')
         print_indented(pprint.pformat(renames, width=200, sort_dicts=True), args.human_readable)

    #show process summary information
    print('{} unique files were found across all source folders'.format(len(d)))
    print('{} sets of duplicate files were found based on SHA256 of their contents'.format(len(collisions)))
    print('{} files were successfully copied to the target folder'.format(len(copies)))
    print('{} filenames were changed during copying because the same filename already existed in the target directory!'.format(len(renames)))
    if args.dry_run:
         print('--dry-run was selected. NO FILES ACTUALLY COPIED!')

    

def main():
	parser = setup_argparser()
	args = parser.parse_args()

	if args.debug:
		print('------------OS Environment---------------', file=sys.stderr)
		for k, v in os.environ.items():
			print(f'{k}={v}', file=sys.stderr)
		print('------------END Environment---------------\n\n', file=sys.stderr)
		sys.stderr.flush()

	try:
		args.func(args)

	except Exception as err:
		print('FAILED')
		print(err)
		sys.exit(1)

if __name__ == '__main__':
	main()
