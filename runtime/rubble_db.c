/*
Rubble Database Module
Provides SQLite database functionality for data persistence.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sqlite3.h"

// Database connection structure
typedef struct {
    sqlite3* db;
    char* error;
} DatabaseConnection;

// Open a database connection
DatabaseConnection* db_open(const char* filename) {
    DatabaseConnection* conn = (DatabaseConnection*)malloc(sizeof(DatabaseConnection));
    conn->error = NULL;
    
    int result = sqlite3_open(filename, &conn->db);
    if (result != SQLITE_OK) {
        conn->error = strdup(sqlite3_errmsg(conn->db));
        sqlite3_close(conn->db);
        conn->db = NULL;
    }
    
    return conn;
}

// Execute a SQL statement (INSERT, UPDATE, DELETE, CREATE TABLE, etc.)
int db_execute(DatabaseConnection* conn, const char* sql) {
    if (!conn || !conn->db) {
        return SQLITE_ERROR;
    }
    
    char* err_msg = NULL;
    int result = sqlite3_exec(conn->db, sql, NULL, NULL, &err_msg);
    
    if (result != SQLITE_OK) {
        if (err_msg) {
            conn->error = strdup(err_msg);
            sqlite3_free(err_msg);
        }
    }
    
    return result;
}

// Query database and return results as JSON string
char* db_query(DatabaseConnection* conn, const char* sql) {
    if (!conn || !conn->db) {
        return strdup("[]");
    }
    
    sqlite3_stmt* stmt;
    int result = sqlite3_prepare_v2(conn->db, sql, -1, &stmt, NULL);
    if (result != SQLITE_OK) {
        conn->error = strdup(sqlite3_errmsg(conn->db));
        return strdup("[]");
    }
    
    // Build JSON array from results
    char* json = strdup("[");
    int first_row = 1;
    int col_count = sqlite3_column_count(stmt);
    
    while (sqlite3_step(stmt) == SQLITE_ROW) {
        if (!first_row) {
            char* temp = json;
            json = (char*)malloc(strlen(json) + 2);
            strcpy(json, temp);
            strcat(json, ",");
            free(temp);
        }
        
        char* row_json = strdup("{");
        for (int i = 0; i < col_count; i++) {
            const char* col_name = sqlite3_column_name(stmt, i);
            int col_type = sqlite3_column_type(stmt, i);
            
            if (i > 0) {
                char* temp = row_json;
                row_json = (char*)malloc(strlen(row_json) + 2);
                strcpy(row_json, temp);
                strcat(row_json, ",");
                free(temp);
            }
            
            // Add column name
            char* temp = row_json;
            row_json = (char*)malloc(strlen(row_json) + strlen(col_name) + 5);
            strcpy(row_json, temp);
            strcat(row_json, "\"");
            strcat(row_json, col_name);
            strcat(row_json, "\":");
            free(temp);
            
            // Add column value
            switch (col_type) {
                case SQLITE_INTEGER: {
                    int value = sqlite3_column_int(stmt, i);
                    char val_str[32];
                    snprintf(val_str, sizeof(val_str), "%d", value);
                    temp = row_json;
                    row_json = (char*)malloc(strlen(row_json) + strlen(val_str) + 1);
                    strcpy(row_json, temp);
                    strcat(row_json, val_str);
                    free(temp);
                    break;
                }
                case SQLITE_FLOAT: {
                    double value = sqlite3_column_double(stmt, i);
                    char val_str[64];
                    snprintf(val_str, sizeof(val_str), "%f", value);
                    temp = row_json;
                    row_json = (char*)malloc(strlen(row_json) + strlen(val_str) + 1);
                    strcpy(row_json, temp);
                    strcat(row_json, val_str);
                    free(temp);
                    break;
                }
                case SQLITE_TEXT: {
                    const char* value = (const char*)sqlite3_column_text(stmt, i);
                    if (value) {
                        temp = row_json;
                        row_json = (char*)malloc(strlen(row_json) + strlen(value) + 3);
                        strcpy(row_json, temp);
                        strcat(row_json, "\"");
                        strcat(row_json, value);
                        strcat(row_json, "\"");
                        free(temp);
                    } else {
                        temp = row_json;
                        row_json = (char*)malloc(strlen(row_json) + 5);
                        strcpy(row_json, temp);
                        strcat(row_json, "null");
                        free(temp);
                    }
                    break;
                }
                case SQLITE_NULL:
                default: {
                    temp = row_json;
                    row_json = (char*)malloc(strlen(row_json) + 5);
                    strcpy(row_json, temp);
                    strcat(row_json, "null");
                    free(temp);
                    break;
                }
            }
        }
        
        temp = row_json;
        row_json = (char*)malloc(strlen(row_json) + 2);
        strcpy(row_json, temp);
        strcat(row_json, "}");
        free(temp);
        
        temp = json;
        json = (char*)malloc(strlen(json) + strlen(row_json) + 1);
        strcpy(json, temp);
        strcat(json, row_json);
        free(temp);
        free(row_json);
        
        first_row = 0;
    }
    
    sqlite3_finalize(stmt);
    
    char* temp = json;
    json = (char*)malloc(strlen(json) + 2);
    strcpy(json, temp);
    strcat(json, "]");
    free(temp);
    
    return json;
}

// Close database connection
void db_close(DatabaseConnection* conn) {
    if (conn) {
        if (conn->db) {
            sqlite3_close(conn->db);
        }
        if (conn->error) {
            free(conn->error);
        }
        free(conn);
    }
}

// Get last error message
char* db_error(DatabaseConnection* conn) {
    if (conn && conn->error) {
        return conn->error;
    }
    return NULL;
}
