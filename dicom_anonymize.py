#!/usr/bin/env python

from pathlib import Path
from argparse import ArgumentParser, Namespace, ArgumentDefaultsHelpFormatter

from chris_plugin import chris_plugin, PathMapper
import pydicom

__version__ = '1.0.0'

DISPLAY_TITLE = r"""
       _           _ _                                                              _         
      | |         | (_)                                                            (_)        
 _ __ | |______ __| |_  ___ ___  _ __ ___    __ _ _ __   ___  _ __  _   _ _ __ ___  _ _______ 
| '_ \| |______/ _` | |/ __/ _ \| '_ ` _ \  / _` | '_ \ / _ \| '_ \| | | | '_ ` _ \| |_  / _ \
| |_) | |     | (_| | | (_| (_) | | | | | || (_| | | | | (_) | | | | |_| | | | | | | |/ /  __/
| .__/|_|      \__,_|_|\___\___/|_| |_| |_| \__,_|_| |_|\___/|_| |_|\__, |_| |_| |_|_/___\___|
| |                                     ______                       __/ |                    
|_|                                    |______|                     |___/                     
"""


parser = ArgumentParser(description='A ChRIS plugin to anonymize header metadata in DICOM files',
                        formatter_class=ArgumentDefaultsHelpFormatter)
parser.add_argument('-p', '--pattern', default='**/*.dcm', type=str,
                    help='input file filter glob')
parser.add_argument('-V', '--version', action='version',
                    version=f'%(prog)s {__version__}')


# The main function of this *ChRIS* plugin is denoted by this ``@chris_plugin`` "decorator."
# Some metadata about the plugin is specified here. There is more metadata specified in setup.py.
#
# documentation: https://fnndsc.github.io/chris_plugin/chris_plugin.html#chris_plugin
@chris_plugin(
    parser=parser,
    title='A ChRIS plugin to anonymize DICOM files',
    category='',                 # ref. https://chrisstore.co/plugins
    min_memory_limit='100Mi',    # supported units: Mi, Gi
    min_cpu_limit='1000m',       # millicores, e.g. "1000m" = 1 CPU core
    min_gpu_limit=0              # set min_gpu_limit=1 to enable GPU
)
def main(options: Namespace, inputdir: Path, outputdir: Path):
    """
    *ChRIS* plugins usually have two positional arguments: an **input directory** containing
    input files and an **output directory** where to write output files. Command-line arguments
    are passed to this main method implicitly when ``main()`` is called below without parameters.

    :param options: non-positional arguments parsed by the parser given to @chris_plugin
    :param inputdir: directory containing (read-only) input files
    :param outputdir: directory where to write output files
    """

    print(DISPLAY_TITLE)

    # Typically it's easier to think of programs as operating on individual files
    # rather than directories. The helper functions provided by a ``PathMapper``
    # object make it easy to discover input files and write to output files inside
    # the given paths.
    #
    # Refer to the documentation for more options, examples, and advanced uses e.g.
    # adding a progress bar and parallelism.
    mapper = PathMapper.file_mapper(inputdir, outputdir, glob=options.pattern, fail_if_empty=False)
    for input_file, output_file in mapper:
        ds = pydicom.dcmread(input_file)
        ds.save_as(output_file)



if __name__ == '__main__':
    main()
