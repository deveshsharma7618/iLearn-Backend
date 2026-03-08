    param(
    [string]$ConfigPath = "bulk_upload/bulk_upload_config.json"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $ConfigPath)) {
    throw "Config file not found: $ConfigPath"
}

$config = Get-Content -Path $ConfigPath -Raw | ConvertFrom-Json

$baseUrl = ($config.base_url).TrimEnd('/')
$token = [string]$config.admin_token
$courseStatus = if ($config.course_status) { [string]$config.course_status } else { "active" }

$contentTitle = [string]$config.content.title
$contentDescription = [string]$config.content.description
$contentType = if ($config.content.content_type) { [string]$config.content.content_type } else { "document" }
$contentFilePath = [string]$config.content.file_path

$resourceEnabled = $false
$resourceTitle = ""
$resourceFilePath = ""
$attachToUploadedContent = $true

if ($null -ne $config.resource) {
    $resourceEnabled = [bool]$config.resource.enabled
    $resourceTitle = [string]$config.resource.title
    $resourceFilePath = [string]$config.resource.file_path
    if ($null -ne $config.resource.attach_to_uploaded_content) {
        $attachToUploadedContent = [bool]$config.resource.attach_to_uploaded_content
    }
}

if ([string]::IsNullOrWhiteSpace($token) -or $token -eq "PASTE_ADMIN_JWT_TOKEN_HERE") {
    throw "Please set admin_token in $ConfigPath"
}

if (!(Test-Path $contentFilePath)) {
    throw "Content file not found: $contentFilePath"
}

if ($resourceEnabled -and !(Test-Path $resourceFilePath)) {
    throw "Resource file not found: $resourceFilePath"
}

Write-Host "Fetching courses..."
$coursesJson = curl.exe --silent --show-error --request GET "$baseUrl/api/courses?status=$courseStatus"
$coursesResponse = $coursesJson | ConvertFrom-Json

if ($null -eq $coursesResponse.courses -or $coursesResponse.courses.Count -eq 0) {
    Write-Host "No courses found for status '$courseStatus'."
    exit 0
}

$successCount = 0
$failedCount = 0

foreach ($course in $coursesResponse.courses) {
    $courseId = [string]$course._id
    $courseName = [string]$course.name

    Write-Host "Uploading content to course: $courseName ($courseId)"

    try {
        $contentUploadRaw = curl.exe --silent --show-error --request POST "$baseUrl/api/courses/$courseId/content/upload" `
            --header "Authorization: Bearer $token" `
            --form "file=@$contentFilePath" `
            --form "title=$contentTitle" `
            --form "description=$contentDescription" `
            --form "content_type=$contentType"

        $contentUpload = $contentUploadRaw | ConvertFrom-Json

        if ($contentUpload.error) {
            throw "Content upload failed: $($contentUpload.error)"
        }

        $uploadedContentId = [string]$contentUpload.content.content_id

        if ($resourceEnabled) {
            Write-Host "Uploading resource to course: $courseName ($courseId)"

            $curlArgs = @(
                "--silent",
                "--show-error",
                "--request", "POST",
                "$baseUrl/api/courses/$courseId/resources/upload",
                "--header", "Authorization: Bearer $token",
                "--form", "file=@$resourceFilePath",
                "--form", "title=$resourceTitle"
            )

            if ($attachToUploadedContent -and -not [string]::IsNullOrWhiteSpace($uploadedContentId)) {
                $curlArgs += @("--form", "content_id=$uploadedContentId")
            }

            $resourceUploadRaw = & curl.exe @curlArgs
            $resourceUpload = $resourceUploadRaw | ConvertFrom-Json

            if ($resourceUpload.error) {
                throw "Resource upload failed: $($resourceUpload.error)"
            }
        }

        $successCount++
        Write-Host "Success: $courseName"
    }
    catch {
        $failedCount++
        Write-Warning "Failed for $courseName ($courseId): $($_.Exception.Message)"
    }
}

Write-Host "Bulk upload complete. Success: $successCount, Failed: $failedCount"
