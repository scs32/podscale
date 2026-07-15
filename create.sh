#!/usr/bin/env bash
set -euo pipefail

# Directory where the Tailarr scripts are located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load utilities
source "$SCRIPT_DIR/error-handler.sh"
source "$SCRIPT_DIR/logging-utils.sh"

# Main entry point for service creation
main() {
    setup_error_handler
    
    log_info "Starting service deployment..."
    
    # Read configuration from stdin
    local config_json
    config_json="$(cat)"
    
    if [[ -z "$config_json" ]]; then
        log_error "No JSON input provided"
        exit 1
    fi
    
    # Save config for debugging (contains no secrets - only the key file
    # path). Best-effort: the CWD may be invalid or read-only.
    echo "$config_json" > ./.last-config.json 2>/dev/null || true

    # Parse basic service info
    source "$SCRIPT_DIR/parse-service-config.sh"
    local service_info
    service_info=$(parse_service_config "$config_json")

    # The target log dir is now known: point the deployment log at the
    # service dir (unless the caller pinned an absolute LOG_FILE via env).
    # init_logging never fails — a deploy must not die over a log file.
    local service_dir
    service_dir=$(jq -r '.service_dir' <<<"$service_info")
    init_logging "$service_dir"

    # Create service directory structure
    source "$SCRIPT_DIR/setup-service-env.sh"
    setup_service_environment "$service_info"
    
    # Generate all management scripts
    source "$SCRIPT_DIR/generate-scripts.sh"
    generate_all_scripts "$service_info"

    # Persist the parsed config beside the scripts (no secrets - the auth
    # key travels as a file path only). Used by update tooling.
    echo "$service_info" > "$service_dir/.config.json"
    
    # Display completion message
    source "$SCRIPT_DIR/display-summary.sh"
    display_service_summary "$service_info"
    
    log_info "Service deployment completed successfully"
}

# Call main if script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
