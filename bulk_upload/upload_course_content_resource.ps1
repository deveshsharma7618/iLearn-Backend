param(
    [string]$ConfigPath = "bulk_upload/single_course_upload_config.json"
)

$ErrorActionPreference = "Stop"

function Resolve-ProjectPath {
    param([string]$PathValue)

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return $PathValue
    }

    return [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $PathValue))
}

function Invoke-MultipartUpload {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$BearerToken,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $false)][hashtable]$FormFields
    )

    $resolvedFilePath = Resolve-ProjectPath -PathValue $FilePath
    if (-not (Test-Path $resolvedFilePath)) {
        throw "File not found: $resolvedFilePath"
    }

    $boundary = "----iLearnBoundary$([Guid]::NewGuid().ToString('N'))"
    $lineBreak = "`r`n"
    $encoding = [System.Text.Encoding]::UTF8

    $request = [System.Net.HttpWebRequest]::Create($Url)
    $request.Method = "POST"
    $request.ContentType = "multipart/form-data; boundary=$boundary"
    $request.Accept = "application/json"
    $request.Headers.Add("Authorization", "Bearer $BearerToken")

    $requestStream = $request.GetRequestStream()

    try {
        if ($FormFields) {
            foreach ($key in $FormFields.Keys) {
                $value = "$($FormFields[$key])"
                if (-not [string]::IsNullOrWhiteSpace($value)) {
                    $fieldPart = "--$boundary$lineBreak" +
                        "Content-Disposition: form-data; name=`"$key`"$lineBreak$lineBreak" +
                        "$value$lineBreak"
                    $fieldBytes = $encoding.GetBytes($fieldPart)
                    $requestStream.Write($fieldBytes, 0, $fieldBytes.Length)
                }
            }
        }

        $fileName = [System.IO.Path]::GetFileName($resolvedFilePath)
        $fileHeader = "--$boundary$lineBreak" +
            "Content-Disposition: form-data; name=`"file`"; filename=`"$fileName`"$lineBreak" +
            "Content-Type: application/octet-stream$lineBreak$lineBreak"
        $fileHeaderBytes = $encoding.GetBytes($fileHeader)
        $requestStream.Write($fileHeaderBytes, 0, $fileHeaderBytes.Length)

        $fileBytes = [System.IO.File]::ReadAllBytes($resolvedFilePath)
        $requestStream.Write($fileBytes, 0, $fileBytes.Length)

        $lineBreakBytes = $encoding.GetBytes($lineBreak)
        $requestStream.Write($lineBreakBytes, 0, $lineBreakBytes.Length)

        $closingBoundary = "--$boundary--$lineBreak"
        $closingBoundaryBytes = $encoding.GetBytes($closingBoundary)
        $requestStream.Write($closingBoundaryBytes, 0, $closingBoundaryBytes.Length)
    }
    finally {
        $requestStream.Close()
    }

    $isSuccessStatusCode = $true
    $statusCode = 0
    $responseBody = ""

    try {
        $response = [System.Net.HttpWebResponse]$request.GetResponse()
    }
    catch [System.Net.WebException] {
        if ($_.Exception.Response) {
            $response = [System.Net.HttpWebResponse]$_.Exception.Response
            $isSuccessStatusCode = $false
        }
        else {
            throw
        }
    }

    try {
        $statusCode = [int]$response.StatusCode
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream())
        try {
            $responseBody = $reader.ReadToEnd()
        }
        finally {
            $reader.Close()
        }
    }
    finally {
        $response.Close()
    }

    if ($statusCode -ge 200 -and $statusCode -lt 300) {
        $isSuccessStatusCode = $true
    }

    $parsedBody = $null
    try {
        $parsedBody = $responseBody | ConvertFrom-Json
    }
    catch {
        $parsedBody = $responseBody
    }

    [PSCustomObject]@{
        IsSuccessStatusCode = $isSuccessStatusCode
        StatusCode = $statusCode
        Body = $parsedBody
    }
}

try {
    $resolvedConfigPath = Resolve-ProjectPath -PathValue $ConfigPath
    if (-not (Test-Path $resolvedConfigPath)) {
        throw "Config file not found: $resolvedConfigPath"
    }

    $config = Get-Content -Path $resolvedConfigPath -Raw | ConvertFrom-Json

    $apiBaseUrl = "$($config.api_base_url)".TrimEnd('/')
    $adminToken = "$($config.admin_token)"
    $courseId = "$($config.course_id)"

    if ([string]::IsNullOrWhiteSpace($apiBaseUrl)) { throw "api_base_url is required in config" }
    if ([string]::IsNullOrWhiteSpace($adminToken) -or $adminToken -eq "PASTE_ADMIN_JWT_TOKEN_HERE") { throw "admin_token is required in config" }
    if ([string]::IsNullOrWhiteSpace($courseId) -or $courseId -eq "PASTE_COURSE_ID_HERE") { throw "course_id is required in config" }

    $contentUrl = "$apiBaseUrl/api/courses/$courseId/content/upload"
    $resourceUrl = "$apiBaseUrl/api/courses/$courseId/resources/upload"

    Write-Host "Uploading content to course $courseId ..." -ForegroundColor Cyan
    $contentFields = @{
        title = "$($config.content.title)"
        description = "$($config.content.description)"
        content_type = "$($config.content.content_type)"
    }

    $contentResult = Invoke-MultipartUpload -Url $contentUrl -BearerToken $adminToken -FilePath "$($config.content.file_path)" -FormFields $contentFields

    if (-not $contentResult.IsSuccessStatusCode) {
        Write-Host "Content upload failed (HTTP $($contentResult.StatusCode))" -ForegroundColor Red
        $contentResult.Body | ConvertTo-Json -Depth 10
        exit 1
    }

    Write-Host "Content upload successful (HTTP $($contentResult.StatusCode))" -ForegroundColor Green
    $contentResult.Body | ConvertTo-Json -Depth 10

    $uploadedContentId = $null
    try {
        $uploadedContentId = $contentResult.Body.content.content_id
    }
    catch {
        $uploadedContentId = $null
    }

    $resourceContentId = "$($config.resource.content_id)"
    $attachToUploaded = [bool]$config.resource.attach_to_uploaded_content
    if ([string]::IsNullOrWhiteSpace($resourceContentId) -and $attachToUploaded -and -not [string]::IsNullOrWhiteSpace($uploadedContentId)) {
        $resourceContentId = $uploadedContentId
    }

    Write-Host "Uploading resource to course $courseId ..." -ForegroundColor Cyan
    $resourceFields = @{
        title = "$($config.resource.title)"
    }

    if (-not [string]::IsNullOrWhiteSpace($resourceContentId)) {
        $resourceFields["content_id"] = $resourceContentId
    }

    $resourceResult = Invoke-MultipartUpload -Url $resourceUrl -BearerToken $adminToken -FilePath "$($config.resource.file_path)" -FormFields $resourceFields

    if (-not $resourceResult.IsSuccessStatusCode) {
        Write-Host "Resource upload failed (HTTP $($resourceResult.StatusCode))" -ForegroundColor Red
        $resourceResult.Body | ConvertTo-Json -Depth 10
        exit 1
    }

    Write-Host "Resource upload successful (HTTP $($resourceResult.StatusCode))" -ForegroundColor Green
    $resourceResult.Body | ConvertTo-Json -Depth 10

    Write-Host "Upload flow completed." -ForegroundColor Green
}
catch {
    Write-Host "Script failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
