#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AutoGIS command-line entry point.

The command accepts a natural-language geospatial request, retrieves data when
needed, generates PyQGIS code, and can execute that code in a configured QGIS
environment.

Examples:
    python run_analysis.py
    python run_analysis.py "Download Sentinel-2 imagery for Beijing and calculate NDVI"
    python run_analysis.py --no-run "Create a 500-meter buffer around D:/data/roads.shp"
"""

import argparse
import sys
import os
from pathlib import Path

# Make project packages importable when the script is run directly.
sys.path.insert(0, str(Path(__file__).parent))

from spatial_analysis_system import (
    Config,
    WorkflowEngine,
    TaskType,
)


def print_banner():
    """Print the AutoGIS startup banner."""
    banner = r"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║     █████╗ ██╗   ██╗████████╗ ██████╗  ██████╗ ██╗███████╗    ║
    ║    ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗██╔════╝ ██║██╔════╝    ║
    ║    ███████║██║   ██║   ██║   ██║   ██║██║  ███╗██║███████╗    ║
    ║    ██╔══██║██║   ██║   ██║   ██║   ██║██║   ██║██║╚════██║    ║
    ║    ██║  ██║╚██████╔╝   ██║   ╚██████╔╝╚██████╔╝██║███████║    ║
    ║    ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝  ╚═════╝ ╚═╝╚══════╝    ║
    ║                                                               ║
    ║         Automated Geospatial Analysis System v1.0.0           ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def print_help_message():
    """Print interactive-mode instructions and examples."""
    help_text = """
Usage:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Data retrieval only:
   Examples:
   - "Download Sentinel-2 imagery for Beijing"
   - "Get road data for Shanghai"
   - "Find points of interest around West Lake"

2. Data retrieval and analysis:
   Examples:
   - "Download Beijing road data and create a 1,000-meter buffer"
   - "Get Sentinel-2 imagery for Shanghai and calculate NDVI"
   - "Download land-use data for West Lake and clip it to the study area"

3. Analysis using existing local data:
   Examples:
   - "Create a 500-meter buffer around D:/data/roads.shp"
   - "Clip D:/data/landuse.tif with D:/data/boundary.shp"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Commands:
   - Enter a request and press Enter to run it.
   - Enter 'help' to show this message.
   - Enter 'config' to display the active configuration.
   - Enter 'quit' or 'exit' to leave the program.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    print(help_text)


def print_config(config: Config):
    """Print the active runtime configuration."""
    print("\nActive configuration:")
    print("━" * 50)
    print(f"  LLM model: {config.llm.model_name}")
    print(f"  API base URL: {config.llm.base_url}")
    print(f"  Skip data download: {config.workflow.skip_data_download}")
    print(f"  Run generated scripts automatically: {config.workflow.auto_run_script}")
    print(f"  Optimize failed code automatically: {config.workflow.auto_optimize_on_failure}")
    print(f"  Maximum optimization rounds: {config.workflow.max_optimization_rounds}")
    print(f"  Generated-script directory: {config.output.script_output_dir}")
    print(f"  Result directory: {config.output.result_output_dir}")
    print("━" * 50)


def interactive_mode(engine: WorkflowEngine, config: Config):
    """Run the interactive command-line session."""
    # print_banner()
    print_help_message()
    
    while True:
        try:
            query = input("\nEnter a geospatial analysis request ('help' or 'quit'): ").strip()
            
            if not query:
                continue
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("\nThank you for using AutoGIS. Goodbye!")
                break
            
            if query.lower() == 'help':
                print_help_message()
                continue
            
            if query.lower() == 'config':
                print_config(config)
                continue
            
            result = engine.process(query)
            
            print("\n" + "=" * 60)
            print("Execution summary")
            print("=" * 60)
            print(f"  Status: {'Success' if result.success else 'Failed'}")
            print(f"  Task type: {result.task_type.value}")
            
            if result.downloaded_files:
                print(f"  Downloaded files: {len(result.downloaded_files)}")
                for f in result.downloaded_files[:3]:
                    print(f"    - {Path(f).name}")
                if len(result.downloaded_files) > 3:
                    print(f"    ... and {len(result.downloaded_files) - 3} more")
            
            if result.code_file_path:
                print(f"  Generated script: {Path(result.code_file_path).name}")
            
            if result.optimization_rounds > 0:
                print(f"  Optimization rounds: {result.optimization_rounds}")
            
            if result.output_files:
                print(f"  Output files: {len(result.output_files)}")
                for f in result.output_files:
                    print(f"    - {Path(f).name}")
            
            if result.message:
                print(f"  Message: {result.message}")
            
            if result.warnings:
                print(f"  Warnings: {', '.join(result.warnings)}")
            
            engine.save_result(result)
            
        except KeyboardInterrupt:
            print("\n\nInterrupt received. Exiting...")
            break
        except Exception as e:
            print(f"\nExecution error: {e}")
            import traceback
            traceback.print_exc()


def main():
    """Parse CLI arguments and run one request or the interactive session."""
    parser = argparse.ArgumentParser(
        description="AutoGIS automated geospatial analysis system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_analysis.py                                      # Interactive mode
  python run_analysis.py "Download road data for Beijing"     # Run a request
  python run_analysis.py --skip-download "Create a buffer"    # Use local data only
  python run_analysis.py --no-run "Generate NDVI code"        # Do not execute QGIS
"""
    )
    
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Geospatial analysis request; starts interactive mode when omitted"
    )
    
    parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to the YAML configuration file"
    )
    
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip the data retrieval step"
    )
    
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Do not execute generated scripts automatically"
    )
    
    parser.add_argument(
        "--no-optimize",
        action="store_true",
        help="Do not optimize failed code automatically"
    )
    
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Maximum code-optimization rounds"
    )
    
    parser.add_argument(
        "--api-key",
        default=None,
        help="LLM API Key"
    )
    
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model name"
    )
    
    args = parser.parse_args()
    
    config = Config(args.config)
    
    if args.skip_download:
        config.workflow.skip_data_download = True
    if args.no_run:
        config.workflow.auto_run_script = False
    if args.no_optimize:
        config.workflow.auto_optimize_on_failure = False
    if args.max_rounds is not None:
        config.workflow.max_optimization_rounds = args.max_rounds
    if args.api_key:
        config.llm.api_key = args.api_key
    if args.model:
        config.llm.model_name = args.model
    
    if not config.llm.api_key:
        print("Error: no LLM API key is configured.")
        print("Set llm.api_key in spatial_analysis_system/config.yaml, provide --api-key, or set AUTOGIS_API_KEY or OPENAI_API_KEY.")
        sys.exit(1)
    
    try:
        engine = WorkflowEngine(config)
    except Exception as e:
        print(f"Failed to initialize the workflow engine: {e}")
        sys.exit(1)
    
    # Run a single request or start the interactive session.
    if args.query:
        result = engine.process(args.query)
        engine.save_result(result)
        
        sys.exit(0 if result.success else 1)
    else:
        interactive_mode(engine, config)


if __name__ == "__main__":
    main()

