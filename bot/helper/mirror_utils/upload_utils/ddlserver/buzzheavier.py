#!/usr/bin/env python3
from os import path as ospath
from aiofiles.os import path as aiopath
from aiohttp import ClientSession
import asyncio

from bot import LOGGER

class BuzzHeavier:
    def __init__(self, dluploader=None, api_key=None):
        self.api_url = "https://w.buzzheavier.com"
        self.dluploader = dluploader
        self.api_key = api_key
        if api_key:
            LOGGER.info(f"BuzzHeavier initialized with API key: {api_key[:8]}...")
        else:
            LOGGER.warning("BuzzHeavier initialized without an API key. Some features may not work.")

    async def upload_file(self, file_path):
        """Upload a single file to BuzzHeavier"""
        LOGGER.info(f"Starting BuzzHeavier upload for: {file_path}")
        if not await aiopath.exists(file_path):
            raise Exception(f"File not found: {file_path}")
        
        if self.dluploader.is_cancelled:
            LOGGER.info("Upload cancelled by user")
            return

        file_name = ospath.basename(file_path)
        LOGGER.info(f"Uploading file: {file_name}")
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Connection': 'keep-alive',
            'keep-alive': '300',
            'Expect': '100-continue'
        }
        
        upload_url = f"{self.api_url}/{file_name}?locationId=12brteedoy0f"
        
        try:
            self.dluploader.last_uploaded = 0
            result = await asyncio.wait_for(
                self.dluploader.upload_aiohttp(
                    upload_url,
                    file_path,
                    None,  # No req_file needed for PUT
                    {},     # No data needed for PUT
                    headers=headers,
                    method='PUT'
                ), timeout=3600
            )
            
            if not result:
                raise Exception("Upload failed - no response from server")
                
            if isinstance(result, str):
                LOGGER.error(f"Unexpected response: {result}")
                raise Exception("Invalid server response")
                
            if result.get('code') not in [200, 201]:
                LOGGER.error(f"Upload failed: {result}")
                raise Exception(f"Upload failed with code {result.get('code')}")
                
            file_id = result.get('data', {}).get('id')
            if not file_id:
                LOGGER.error(f"Could not extract file ID from response: {result}")
                raise Exception("Could not extract file ID from response")
                
            download_url = f"https://buzzheavier.com/{file_id}"
            return {"downloadPage": download_url}
                
        except Exception as e:
            LOGGER.error(f"Error uploading to BuzzHeavier: {str(e)}")
            raise

    async def upload(self, file_path):
        """Main upload method"""
        LOGGER.info(f"BuzzHeavier upload called for: {file_path}")
        if await aiopath.isfile(file_path):
            result = await self.upload_file(file_path)
            LOGGER.info(f"Upload result: {result}")
            if result and result.get('downloadPage'):
                return result['downloadPage']  # Return direct URL for DDLEngine
        else:
            raise Exception("BuzzHeavier doesn't support folder uploads!")
        
        if self.dluploader.is_cancelled:
            return
            
        raise Exception("Failed to upload file to BuzzHeavier")
