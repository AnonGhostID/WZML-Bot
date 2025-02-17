#!/usr/bin/env python3
from os import path as ospath
from aiofiles.os import path as aiopath
from aiohttp import ClientSession
import base64

from bot import LOGGER
from bot.helper.mirror_utils.upload_utils.progress_file_reader import ProgressFileReader

class PixelDrain:
    def __init__(self, dluploader=None, api_key=None):
        self.api_url = "https://pixeldrain.com/api"
        self.dluploader = dluploader
        if not api_key:
            raise Exception("PixelDrain API Key is required! Get it from https://pixeldrain.com/api")
        self.api_key = api_key
        self.auth_header = f"Basic {base64.b64encode(f':{api_key}'.encode()).decode()}"
        LOGGER.info(f"PixelDrain initialized with API key: {api_key[:8]}...")

    async def upload_file(self, file_path):
        """Upload a single file to PixelDrain"""
        LOGGER.info(f"Starting PixelDrain upload for: {file_path}")
        if not await aiopath.exists(file_path):
            raise Exception(f"File not found: {file_path}")
        
        if self.dluploader.is_cancelled:
            LOGGER.info("Upload cancelled by user")
            return

        file_name = ospath.basename(file_path)
        LOGGER.info(f"Uploading file: {file_name}")
        
        headers = {
            'Authorization': self.auth_header,
            'Content-Type': 'application/octet-stream'
        }
        
        upload_url = f"{self.api_url}/file/{file_name}"
        
        try:
            async with ClientSession() as session:
                LOGGER.info("Starting file upload...")
                with ProgressFileReader(filename=file_path, read_callback=self.dluploader.__progress_callback) as file:
                    async with session.put(upload_url, data=file, headers=headers) as resp:
                        
                        if resp.status >= 400:
                            try:
                                error = await resp.json()
                                LOGGER.error(f"PixelDrain upload failed: {error}")
                                raise Exception(f"Upload failed: {error.get('message', 'Unknown error')}")
                            except:
                                raise Exception(f"Upload failed with status {resp.status}")
                        

                        if resp.status == 201:
                            response_text = await resp.text()
                            try:
                                import json
                                json_response = json.loads(response_text)
                                file_id = json_response.get('id')
                                if file_id:
                                    download_url = f"https://pixeldrain.com/u/{file_id}"
                                    return {"downloadPage": download_url}
                            except json.JSONDecodeError:
                                # If not JSON, treat as plain text
                                file_id = response_text.strip().strip('"')
                                if file_id:
                                    download_url = f"https://pixeldrain.com/u/{file_id}"
                                    return {"downloadPage": download_url}
                            
                            raise Exception("Could not extract file ID from response")

                        LOGGER.error(f"Upload failed - unexpected response status: {resp.status}")
                        raise Exception("Upload failed - unexpected response status")

        except Exception as e:
            LOGGER.error(f"Error uploading to PixelDrain: {str(e)}")
            raise

    async def upload(self, file_path):
        """Main upload method"""
        LOGGER.info(f"PixelDrain upload called for: {file_path}")
        if await aiopath.isfile(file_path):
            result = await self.upload_file(file_path)
            LOGGER.info(f"Upload result: {result}")
            if result and result.get('downloadPage'):
                return result['downloadPage']  # Return direct URL for DDLEngine
        else:
            raise Exception("Ga support upload Folder!")
        
        if self.dluploader.is_cancelled:
            return
            
        raise Exception("Failed to upload file to PixelDrain")