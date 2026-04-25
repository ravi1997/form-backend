#!/bin/bash

# RIDP Form Platform — Backup and Restore Tool
# This script handles MongoDB, DuckDB, and local file backups.

# --- Configuration ---
BACKUP_DIR="./backups"
MONGO_CONTAINER="shared-mongo"
MONGO_DB="form_backend"
MONGO_USER="root"
MONGO_PASS="rootpassword"
MONGO_AUTH_DB="admin"
ANALYTICS_FILE="analytics.duckdb"
UPLOADS_DIR="uploads"

# ANSI colors
CYAN='\033[36m'
GREEN='\033[32m'
YELLOW='\033[33m'
RED='\033[31m'
RESET='\033[0m'

# --- Functions ---

show_help() {
    echo -e "${CYAN}RIDP Form Platform Backup/Restore Tool${RESET}"
    echo "Usage:"
    echo "  $0 backup           Create a new backup"
    echo "  $0 restore <file>   Restore from a specific backup file (.tar.gz)"
    echo "  $0 list              List existing backups"
}

check_dependencies() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: docker is not installed.${RESET}"
        exit 1
    fi
    if ! docker ps | grep -q "${MONGO_CONTAINER}"; then
        echo -e "${RED}Error: Container ${MONGO_CONTAINER} is not running.${RESET}"
        exit 1
    fi
}

do_backup() {
    check_dependencies
    
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    TEMP_BACKUP_DIR="${BACKUP_DIR}/tmp_${TIMESTAMP}"
    mkdir -p "${TEMP_BACKUP_DIR}"

    echo -e "${CYAN}Starting backup process...${RESET}"

    # 1. MongoDB Backup
    echo -e "${YELLOW}[1/3] Backing up MongoDB...${RESET}"
    docker exec "${MONGO_CONTAINER}" mongodump \
        --username "${MONGO_USER}" \
        --password "${MONGO_PASS}" \
        --authenticationDatabase "${MONGO_AUTH_DB}" \
        --db "${MONGO_DB}" \
        --archive --gzip > "${TEMP_BACKUP_DIR}/mongodb.archive.gz"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ MongoDB backup successful.${RESET}"
    else
        echo -e "${RED}❌ MongoDB backup failed!${RESET}"
        rm -rf "${TEMP_BACKUP_DIR}"
        exit 1
    fi

    # 2. DuckDB Analytics Backup
    echo -e "${YELLOW}[2/3] Backing up Analytics data...${RESET}"
    if [ -f "${ANALYTICS_FILE}" ]; then
        cp "${ANALYTICS_FILE}" "${TEMP_BACKUP_DIR}/"
        echo -e "${GREEN}✅ Analytics DuckDB backed up.${RESET}"
    else
        echo -e "${YELLOW}⚠️  Analytics DuckDB not found, skipping.${RESET}"
    fi

    # 3. Uploads Directory Backup
    echo -e "${YELLOW}[3/3] Backing up Uploads...${RESET}"
    if [ -d "${UPLOADS_DIR}" ]; then
        cp -r "${UPLOADS_DIR}" "${TEMP_BACKUP_DIR}/"
        echo -e "${GREEN}✅ Uploads directory backed up.${RESET}"
    else
        # Try to find uploads in container if not on host
        docker exec "${MONGO_CONTAINER}" ls -d /app/uploads &> /dev/null
        if [ $? -eq 0 ]; then
             docker cp forms_backend:/app/uploads "${TEMP_BACKUP_DIR}/"
             echo -e "${GREEN}✅ Uploads directory copied from container.${RESET}"
        else
             echo -e "${YELLOW}⚠️  Uploads directory not found, skipping.${RESET}"
        fi
    fi

    # Create final archive
    FINAL_ARCHIVE="${BACKUP_DIR}/form_platform_backup_${TIMESTAMP}.tar.gz"
    tar -czf "${FINAL_ARCHIVE}" -C "${TEMP_BACKUP_DIR}" .
    
    rm -rf "${TEMP_BACKUP_DIR}"
    
    echo -e "${GREEN}========================================${RESET}"
    echo -e "${GREEN}Backup complete: ${FINAL_ARCHIVE}${RESET}"
    echo -e "${GREEN}========================================${RESET}"
}

do_restore() {
    BACKUP_FILE=$1
    if [ -z "${BACKUP_FILE}" ]; then
        echo -e "${RED}Error: No backup file specified.${RESET}"
        exit 1
    fi

    if [ ! -f "${BACKUP_FILE}" ]; then
        echo -e "${RED}Error: File ${BACKUP_FILE} not found.${RESET}"
        exit 1
    fi

    check_dependencies

    echo -e "${RED}⚠️  WARNING: This will overwrite existing data!${RESET}"
    read -p "Are you sure you want to proceed? [y/N]: " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo "Restore cancelled."
        exit 0
    fi

    TEMP_RESTORE_DIR="${BACKUP_DIR}/restore_tmp_$(date +%s)"
    mkdir -p "${TEMP_RESTORE_DIR}"
    
    echo -e "${CYAN}Extracting backup...${RESET}"
    tar -xzf "${BACKUP_FILE}" -C "${TEMP_RESTORE_DIR}"

    # 1. MongoDB Restore
    if [ -f "${TEMP_RESTORE_DIR}/mongodb.archive.gz" ]; then
        echo -e "${YELLOW}Restoring MongoDB...${RESET}"
        docker exec -i "${MONGO_CONTAINER}" mongorestore \
            --username "${MONGO_USER}" \
            --password "${MONGO_PASS}" \
            --authenticationDatabase "${MONGO_AUTH_DB}" \
            --archive --gzip --drop < "${TEMP_RESTORE_DIR}/mongodb.archive.gz"
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ MongoDB restore successful.${RESET}"
        else
            echo -e "${RED}❌ MongoDB restore failed!${RESET}"
        fi
    fi

    # 2. DuckDB Restore
    if [ -f "${TEMP_RESTORE_DIR}/${ANALYTICS_FILE}" ]; then
        echo -e "${YELLOW}Restoring Analytics DuckDB...${RESET}"
        cp "${TEMP_RESTORE_DIR}/${ANALYTICS_FILE}" "./${ANALYTICS_FILE}"
        echo -e "${GREEN}✅ Analytics DuckDB restored.${RESET}"
    fi

    # 3. Uploads Restore
    if [ -d "${TEMP_RESTORE_DIR}/${UPLOADS_DIR}" ]; then
        echo -e "${YELLOW}Restoring Uploads...${RESET}"
        cp -r "${TEMP_RESTORE_DIR}/${UPLOADS_DIR}" "./"
        echo -e "${GREEN}✅ Uploads directory restored.${RESET}"
    fi

    rm -rf "${TEMP_RESTORE_DIR}"
    echo -e "${GREEN}========================================${RESET}"
    echo -e "${GREEN}Restore process finished.${RESET}"
    echo -e "${GREEN}========================================${RESET}"
}

list_backups() {
    if [ ! -d "${BACKUP_DIR}" ]; then
        echo "No backups directory found."
        return
    fi
    echo -e "${CYAN}Available Backups:${RESET}"
    ls -lh "${BACKUP_DIR}"/*.tar.gz 2>/dev/null || echo "No backup files found."
}

# --- Main ---

case "$1" in
    backup)
        do_backup
        ;;
    restore)
        do_restore "$2"
        ;;
    list)
        list_backups
        ;;
    *)
        show_help
        ;;
esac
