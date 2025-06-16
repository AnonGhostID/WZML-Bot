#!/usr/bin/env python3
from os import path as ospath
from aiofiles.os import path as aiopath, stat as aiostat
from aiohttp import ClientSession
import asyncio

from bot import LOGGER

class Ranoz:
    def __init__(self, dluploader=None, api_key=None):
        self.api_url = "https://ranoz.gg/api/v1"
        self.dluploader = dluploader
        self.api_key = api_key
        if api_key:
            LOGGER.info(f"Ranoz initialized with API key: {api_key[:8]}...")
        else:
            LOGGER.warning("Ranoz initialized without an API key. Some features may not work.")

    @staticmethod
    async def is_ranozapi(token):
        """Validate Ranoz API key"""
        if token is None:
            return False

        try:
            async with ClientSession() as session:
                headers = {'Authorization': f'Bearer {token}'}
                async with session.get(
                    "https://ranoz.gg/api/v1/account", headers=headers
                ) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        return result.get('success', False)
                    return False
        except Exception:
            return False

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
        
        try:
            # Step 1: Get pre-signed upload URL
            async with ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
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
                    
                    response_data = await resp.json()
                    LOGGER.info(f"Upload URL response: {response_data}")
                    
                    if not response_data.get('data'):
                        raise Exception("No data in upload URL response")
                    
                    upload_url = response_data['data'].get('upload_url')
                    file_data = response_data['data']
                    
                    if not upload_url:
                        raise Exception("No upload URL in response")
            
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
            
            # Extract file information from the first response (not the PUT response)
            file_id = file_data.get('id') or file_data.get('file_id') or file_data.get('key')
            file_url = file_data.get('url') or file_data.get('download_url')
            
            if file_url:
                download_url = file_url
            elif file_id:
                download_url = f"https://ranoz.gg/{file_id}"
            else:
                LOGGER.error(f"Could not extract file URL/ID from response: {file_data}")
                raise Exception("Could not extract file URL from response")
            
            return {"downloadPage": download_url}
                
        except Exception as e:
            LOGGER.error(f"Error uploading to Ranoz: {str(e)}")
            raise

    async def upload(self, file_path):
        """Main upload method"""
        LOGGER.info(f"Ranoz upload called for: {file_path}")
        
        if not self.api_key:
            raise Exception("Ranoz API key is required!")
            
        if not await self.is_ranozapi(self.api_key):
            raise Exception("Invalid Ranoz API Key, please check your account!")
        
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
