/*
Rubble HTTP Module
Provides HTTP client functionality for web API requests.
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#include <wininet.h>
#else
#include <curl/curl.h>
#endif

// HTTP response structure
typedef struct {
    char* body;
    int status_code;
    char* error;
} HttpResponse;

#ifdef _WIN32
// Windows implementation using WinINet
HttpResponse* http_get(const char* url) {
    HttpResponse* response = (HttpResponse*)malloc(sizeof(HttpResponse));
    response->body = NULL;
    response->status_code = 0;
    response->error = NULL;

    HINTERNET hInternet = InternetOpenA("Rubble HTTP Client", INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (!hInternet) {
        response->error = strdup("Failed to initialize WinINet");
        return response;
    }

    HINTERNET hConnect = InternetOpenUrlA(hInternet, url, NULL, 0, INTERNET_FLAG_RELOAD, 0);
    if (!hConnect) {
        response->error = strdup("Failed to open URL");
        InternetCloseHandle(hInternet);
        return response;
    }

    // Read response
    DWORD bytesAvailable;
    DWORD bytesRead;
    char buffer[8192];
    char* body = NULL;
    size_t bodySize = 0;

    while (InternetQueryDataAvailable(hConnect, &bytesAvailable, 0, 0) && bytesAvailable > 0) {
        if (InternetReadFile(hConnect, buffer, sizeof(buffer) - 1, &bytesRead) && bytesRead > 0) {
            buffer[bytesRead] = '\0';
            body = (char*)realloc(body, bodySize + bytesRead + 1);
            memcpy(body + bodySize, buffer, bytesRead);
            bodySize += bytesRead;
            body[bodySize] = '\0';
        }
    }

    response->body = body;
    response->status_code = 200; // WinINet doesn't easily expose status code

    InternetCloseHandle(hConnect);
    InternetCloseHandle(hInternet);

    return response;
}

void http_response_free(HttpResponse* response) {
    if (response) {
        if (response->body) free(response->body);
        if (response->error) free(response->error);
        free(response);
    }
}
#else
// Linux/macOS implementation using libcurl
size_t write_callback(void* contents, size_t size, size_t nmemb, void* userp) {
    size_t totalSize = size * nmemb;
    HttpResponse* response = (HttpResponse*)userp;
    
    response->body = (char*)realloc(response->body, response->status_code + totalSize + 1);
    memcpy(response->body + response->status_code, contents, totalSize);
    response->status_code += totalSize;
    response->body[response->status_code] = '\0';
    
    return totalSize;
}

HttpResponse* http_get(const char* url) {
    HttpResponse* response = (HttpResponse*)malloc(sizeof(HttpResponse));
    response->body = NULL;
    response->status_code = 0;
    response->error = NULL;

    CURL* curl = curl_easy_init();
    if (!curl) {
        response->error = strdup("Failed to initialize curl");
        return response;
    }

    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, response);

    CURLcode res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
        response->error = strdup(curl_easy_strerror(res));
    } else {
        long http_code = 0;
        curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
        // Store the actual body size in status_code temporarily
        response->status_code = (int)strlen(response->body);
    }

    curl_easy_cleanup(curl);
    return response;
}

void http_response_free(HttpResponse* response) {
    if (response) {
        if (response->body) free(response->body);
        if (response->error) free(response->error);
        free(response);
    }
}
#endif
