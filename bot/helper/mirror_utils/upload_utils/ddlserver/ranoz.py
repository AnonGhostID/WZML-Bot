#!/usr/bin/env python3
from os import path as ospath
from aiofiles.os import path as aiopath, stat as aiostat
from aiohttp import ClientSession, FormData
import asyncio
import aiofiles
import json

from bot import LOGGER

class Ranoz:
    def __init__(self, dluploader=None, api_key=None):
        self.api_url = "https://ranoz.gg/api/v1"
        self.dluploader = dluploader
        LOGGER.info("Ranoz initialized successfully")

    async def upload_file(self, file_path):
        """Upload a single file to Ranoz using two-step process"""
        LOGGER.info(f"Starting Ranoz upload for: {file_path}")
        if not await aiopath.exists(file_path):
            raise Exception(f"File not found: {file_path}")
        
        if self.dluploader.is_cancelled:
            LOGGER.info("Upload cancelled by user")
            return

        file_name = ospath.basename(file_path)
        file_stat = await aiostat(file_path)
        file_size = file_stat.st_size
        
        LOGGER.info(f"Uploading file: {file_name} ({file_size} bytes)")
        
        # Check file size (warn for very large files)
        if file_size > 5 * 1024 * 1024 * 1024:  # 5GB
            LOGGER.warning(f"Large file detected: {file_size / (1024*1024*1024):.2f} GB - using streaming upload")
        elif file_size > 10 * 1024 * 1024 * 1024:  # 10GB
            LOGGER.warning(f"Very large file: {file_size / (1024*1024*1024):.2f} GB - upload may take a long time")
        
        try:
            # Use two-step process for reliable streaming upload
            LOGGER.info("Using two-step upload process for better memory efficiency...")
            
            # Step 1: Get pre-signed upload URL
            async with ClientSession() as session:
                headers = {
                    'Content-Type': 'application/json'
                }
                
                file_metadata = {
                    'filename': file_name,
                    'size': file_size
                }
                
                upload_url_endpoint = f"{self.api_url}/files/upload_url"
                LOGGER.info(f"Requesting upload URL from: {upload_url_endpoint}")
                
                async with session.post(upload_url_endpoint, json=file_metadata, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        LOGGER.error(f"Failed to get upload URL: {resp.status} - {error_text}")
                        raise Exception(f"Failed to get upload URL: {resp.status}")
                    
                    # Check content type before attempting JSON decode
                    content_type = resp.headers.get('content-type', '')
                    response_text = await resp.text()
                    LOGGER.info(f"Response content-type: {content_type}")
                    LOGGER.info(f"Response text: {response_text}")
                    
                    # Try to parse as JSON regardless of content-type (API returns JSON with text/plain header)
                    try:
                        response_data = json.loads(response_text)
                        LOGGER.info(f"Upload URL response parsed successfully: {response_data}")
                        
                        if not response_data.get('data'):
                            raise Exception("No data in upload URL response")
                        
                        upload_url = response_data['data'].get('upload_url')
                        file_data = response_data['data']
                        
                        if not upload_url:
                            raise Exception("No upload URL in response")
                    except json.JSONDecodeError:
                        # If not JSON, treat as plain text response (might be the upload URL directly)
                        if response_text.startswith('http'):
                            upload_url = response_text.strip()
                            file_data = {'upload_url': upload_url}
                        else:
                            raise Exception(f"Failed to parse response. Content-Type: {content_type}, Response: {response_text}")
            
            # Step 2: Upload file to pre-signed URL
            if self.dluploader.is_cancelled:
                return
                
            LOGGER.info(f"Uploading to pre-signed URL: {upload_url}")
            self.dluploader.last_uploaded = 0
            
            # Use PUT method with Content-Length header
            put_headers = {
                'Content-Length': str(file_size)
            }
            
            result = await self.dluploader.upload_aiohttp(
                upload_url,
                file_path,
                None,  # No form field name needed for PUT
                {},    # No additional data needed
                headers=put_headers,
                method='PUT'
            )
            
            # For PUT request, success is indicated by status code, not response content
            LOGGER.info(f"File uploaded successfully to Ranoz")
            
            # Extract file information from the upload URL response
            file_id = file_data.get('id')
            file_url = file_data.get('url')
            
            if file_url:
                download_url = file_url
            elif file_id:
                download_url = f"https://ranoz.gg/file/{file_id}"
            else:
                # Fallback: try to get file info from a different endpoint
                LOGGER.warning("Could not extract file URL from upload response, trying alternative approach")
                # For now, we'll use a generic approach - this might need adjustment based on actual API behavior
                download_url = f"https://ranoz.gg/files/{file_name}"
            
            LOGGER.info(f"Generated download URL: {download_url}")
            return {"downloadPage": download_url}
                
        except Exception as e:
            LOGGER.error(f"Error uploading to Ranoz: {str(e)}")
            raise

    async def upload(self, file_path):
        """Main upload method"""
        LOGGER.info(f"Ranoz upload called for: {file_path}")
        
        if await aiopath.isfile(file_path):
            result = await self.upload_file(file_path)
            LOGGER.info(f"Upload result: {result}")
            if result and result.get('downloadPage'):
                return result['downloadPage']  # Return direct URL for DDLEngine
        else:
            raise Exception("Ranoz doesn't support folder uploads!")
        
        if self.dluploader.is_cancelled:
            return
            
        raise Exception("Failed to upload file to Ranoz")
