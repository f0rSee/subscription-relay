from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# HTTP header values must be printable ASCII with no surrounding whitespace.
HeaderValue = Annotated[
    str, Field(min_length=1, max_length=512, pattern=r"^[!-~](?:[ -~]*[!-~])?$")
]


class DeviceSettings(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    user_agent: HeaderValue = "VPNClient/2.0/ios/2731171157721"
    hwid: HeaderValue = "4139def9-6877-4771-b313-49e3119ba158"
    os: HeaderValue = "iOS"
    os_version: HeaderValue = "27.0"
    model: HeaderValue = "iPhone 17 Pro Max"

    def headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/plain, */*",
            "X-HWID": self.hwid,
            "X-Device-OS": self.os,
            "X-Ver-OS": self.os_version,
            "X-Device-Model": self.model,
        }
