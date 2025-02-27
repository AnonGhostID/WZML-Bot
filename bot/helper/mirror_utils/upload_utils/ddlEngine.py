#!/usr/bin/env python3
from pathlib import Path
from traceback import format_exc
from json import JSONDecodeError
from io import BufferedReader
from re import findall as re_findall
from aiofiles.os import path as aiopath
from time import time
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
from aiohttp import ClientSession 
from aiohttp.client_exceptions import ContentTypeError

from bot import LOGGER, user_data
from bot.helper.mirror_utils.upload_utils.ddlserver.gofile import Gofile
from bot.helper.mirror_utils.upload_utils.ddlserver.streamtape import Streamtape
from bot.helper.mirror_utils.upload_utils.ddlserver.pixeldrain import PixelDrain
from bot.helper.mirror_utils.upload_utils.ddlserver.buzzheavier import BuzzHeavier
from bot.helper.ext_utils.fs_utils import get_mime_type
from bot.helper.mirror_utils.upload_utils.progress_file_reader import ProgressFileReader


class DDLUploader:
    def __init__(self, listener=None, name=None, path=None):
        self.name = name
        self.__processed_bytes = 0
        self.last_uploaded = 0
        self.__listener = listener
        self.__path = path
        self.__start_time = time()
        self.total_files = 0
        self.total_folders = 0
        self.is_cancelled = False
        self.__is_errored = False
        self.__ddl_servers = {}
        self.__engine = 'DDL v1'
        self.__asyncSession = None
        self.__user_id = self.__listener.message.from_user.id
    
    async def __user_settings(self):
        user_dict = user_data.get(self.__user_id, {})
        self.__ddl_servers = user_dict.get('ddl_servers', {})
        
    def __progress_callback(self, current):
        chunk_size = current - self.last_uploaded
        self.last_uploaded = current
        self.__processed_bytes += chunk_size

    def _PixelDrain__progress_callback(self, current):
        chunk_size = current - self.last_uploaded
        self.last_uploaded = current
        self.__processed_bytes += chunk_size
    
    @retry(wait=wait_exponential(multiplier=2, min=4, max=8), stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception))
    async def upload_aiohttp(self, url, file_path, req_file, data, headers=None, method='POST'):
        """Modified to support both POST and PUT methods with proper file handling"""
        with ProgressFileReader(filename=file_path, read_callback=self.__progress_callback) as file:
            if method.upper() == 'PUT':
                # For PUT requests (like PixelDrain)
                async with ClientSession() as session:
                    async with session.put(url, data=file, headers=headers) as resp:
                        LOGGER.info(f"Upload response status: {resp.status}")
                        if resp.status in [200, 201]:
                            try:
                                return await resp.json()
                            except ContentTypeError:
                                return await resp.text()
                        else:
                            LOGGER.error(f"Upload failed with status {resp.status}: {await resp.text()}")
                            return None
            else:
                # For POST requests (like GoFile)
                data[req_file] = file
                async with ClientSession() as session:
                    async with session.post(url, data=data, headers=headers) as resp:
                        LOGGER.info(f"Upload response status: {resp.status}")
                        if resp.status == 200:
                            try:
                                return await resp.json()
                            except ContentTypeError:
                                return await resp.text()
                        else:
                            LOGGER.error(f"Upload failed with status {resp.status}: {await resp.text()}")
                            return None

    async def __upload_to_ddl(self, file_path):
        """Modified to better handle upload responses"""
        all_links = {}
        upload_errors = {}  # Track specific errors for each service
        
        for serv, (enabled, api_key) in self.__ddl_servers.items():
            if enabled:
                self.total_files = 0
                self.total_folders = 0
                try:
                    if serv == 'gofile':
                        self.__engine = 'GoFile API'
                        nlink = await Gofile(self, api_key).upload(file_path)
                        if nlink:
                            all_links['GoFile'] = nlink
                    elif serv == 'streamtape':
                        self.__engine = 'StreamTape API'
                        login, key = api_key.split(':')
                        nlink = await Streamtape(self, login, key).upload(file_path)
                        if nlink:
                            all_links['StreamTape'] = nlink
                    elif serv == 'pixeldrain':
                        self.__engine = 'PixelDrain API'
                        nlink = await PixelDrain(self, api_key).upload(file_path)
                        if nlink:
                            all_links['PixelDrain'] = nlink
                    elif serv == 'buzzheavier':
                        self.__engine = 'BuzzHeavier API'
                        nlink = await BuzzHeavier(self, api_key).upload(file_path)
                        if nlink:
                            all_links['BuzzHeavier'] = nlink
                    self.__processed_bytes = 0
                except Exception as e:
                    LOGGER.error(f"Error uploading to {serv}: {str(e)}")
                    upload_errors[serv] = str(e)
                    continue
        
        if not all_links:
            # Construct a more informative error message
            error_msg = []
            for serv, err in upload_errors.items():
                error_msg.append(f"{serv}: {err}")
            
            if error_msg:
                raise Exception(" | ".join(error_msg))
            else:
                raise Exception("No successful uploads completed.")
                
        return all_links

    async def upload(self, file_name, size):
        item_path = f"{self.__path}/{file_name}"
        LOGGER.info(f"Uploading: {item_path} via DDL")
        await self.__user_settings()
        try:
            if await aiopath.isfile(item_path):
                mime_type = get_mime_type(item_path)
            else:
                mime_type = 'Folder'
            link = await self.__upload_to_ddl(item_path)
            if link is None:
                raise Exception('Upload has been manually cancelled!')
            if self.is_cancelled:
                return
            LOGGER.info(f"Uploaded To DDL: {item_path}")
            # Call onUploadComplete with the correct parameters
            await self.__listener.onUploadComplete(link, size, self.total_files, 
                                                 self.total_folders, mime_type, 
                                                 file_name)
            LOGGER.info(f"Task Done: {file_name}")
        except Exception as err:
            LOGGER.info("DDL Upload has been Cancelled")
            if self.__asyncSession:
                await self.__asyncSession.close()
            err = str(err).replace('>', '').replace('<', '')
            LOGGER.info(format_exc())
            await self.__listener.onUploadError(err)
            self.__is_errored = True
        finally:
            # Remove finally block's onUploadComplete call
            # as it's already called in try block
            if self.is_cancelled or self.__is_errored:
                return

    @property
    def speed(self):
        try:
            return self.__processed_bytes / int(time() - self.__start_time)
        except ZeroDivisionError:
            return 0

    @property
    def processed_bytes(self):
        return self.__processed_bytes
    
    @property
    def engine(self):
        return self.__engine

    async def cancel_download(self):
        self.is_cancelled = True
        LOGGER.info(f"Cancelling Upload: {self.name}")
        if self.__asyncSession:
            await self.__asyncSession.close()
        await self.__listener.onUploadError('Your upload has been stopped!')
