#!/usr/bin/env python3

import os, argparse, re, shutil, zipfile, tempfile
from typing import Any, Dict, List, Optional, Union
from types import SimpleNamespace
from pathlib import Path

try:
    import yaml  # type: ignore
except ImportError as exc:  # pragma: no cover - defensive guard for missing dependency
    raise SystemExit("PyYAML is required to build the VSIX. Please run 'pip install pyyaml'.") from exc

SectionEntry = List[Optional[str]]
SectionDefinition = Dict[str, Union[str, SectionEntry]]


def encode_name(name: str) -> bytes:
    try:
        b = name.encode("ascii")
    except UnicodeEncodeError as ex:
        raise ValueError(f"Entry name must be ASCII: {name}") from ex
    return len(b).to_bytes(4, "little") + b

def parse_value(value: Optional[str]) -> bytes:
    if value is None:
        return bytes([0x00])
    
    value = value.strip()

    # ffx########
    match = re.fullmatch(r"([0-9a-fA-F]{2})x([0-9a-fA-F]{8})", value)
    if match:
        flag = int(match.group(1), 16)
        mask = int(match.group(2), 16)
        if flag in (0x00, 0x01):
            raise ValueError(f"Generic flag+mask not allowed for 0x00/0x01: {value}")
        return flag.to_bytes(1, "little") + mask.to_bytes(4, "little")

    # RGB(A) color
    value = value[1:] if value.startswith("#") else value
    if len(value) not in (6, 8):
        raise ValueError(f"Color must be 6 or 8 hex digits: {value}")

    try:
        r = int(value[0:2], 16)
        g = int(value[2:4], 16)
        b = int(value[4:6], 16)
        a = 255 if len(value) == 6 else int(value[6:8], 16)
    except Exception as ex:
        raise ValueError(f"Invalid color hex: {value}") from ex

    return bytes([0x01, r, g, b, a])

def guid_parts(guid: str) -> List[str]:
    p = guid.strip().strip("{}").split("-")
    if len(p) != 5:
        raise ValueError(f"Invalid GUID: {guid}")
    if not re.fullmatch(r"[0-9a-fA-F]{8}", p[0]):
        raise ValueError(f"Invalid GUID: {guid}")
    if not re.fullmatch(r"[0-9a-fA-F]{4}", p[1]):
        raise ValueError(f"Invalid GUID: {guid}")
    if not re.fullmatch(r"[0-9a-fA-F]{4}", p[2]):
        raise ValueError(f"Invalid GUID: {guid}")
    if not re.fullmatch(r"[0-9a-fA-F]{4}", p[3]):
        raise ValueError(f"Invalid GUID: {guid}")
    if not re.fullmatch(r"[0-9a-fA-F]{12}", p[4]):
        raise ValueError(f"Invalid GUID: {guid}")
    return p
    
def guid_str_to_bytes(guid: str) -> bytes:
    p = guid_parts(guid)
    b = bytearray()
    b += int(p[0], 16).to_bytes(4, "little")
    b += int(p[1], 16).to_bytes(2, "little")
    b += int(p[2], 16).to_bytes(2, "little")
    b += bytes.fromhex(p[3])
    b += bytes.fromhex(p[4])
    return bytes(b)

def build_section(theme_guid: str, section_name: str, section: SectionDefinition) -> str:
    if not isinstance(section, dict):
        raise ValueError(f"Section '{section_name}' must map names to 2-element lists!")
    if "GUID" not in section:
        raise ValueError(f"Section '{section_name}' does not have a 'GUID' field!")

    sec: SectionDefinition = dict(section)
    raw_guid = sec.pop("GUID")
    if not isinstance(raw_guid, str):
        raise ValueError(f"Section '{section_name}' GUID must be a string, got {type(raw_guid).__name__}.")
    sec_guid = raw_guid

    blob = bytearray()
    blob += int(0).to_bytes(4, "little") # total length placeholder
    blob += int(11).to_bytes(4, "little")
    blob += int(1).to_bytes(4, "little")
    blob += guid_str_to_bytes(sec_guid)
    blob += int(len(sec)).to_bytes(4, "little")

    for name, entry in sec.items():
        if not isinstance(name, str):
            raise ValueError(f"Entry name '{name}' must be a string.")
        if not isinstance(entry, list) or len(entry) != 2:
            raise ValueError(f"Entry '{name}' must be a 2-element list [x, x]")
        left, right = entry
        blob += encode_name(name)
        blob += parse_value(left)
        blob += parse_value(right)

    blob[0:4] = int(len(blob)).to_bytes(4, "little")

    data: str = f"\n[$RootKey$\\Themes\\{{{theme_guid}}}\\{section_name}]"
    data += f'\n"Data"=hex:{",".join(f"{b:02x}" for b in bytes(blob))}'
    return data

def pkgdef_data(theme: Any, sections: Dict[str, Any]) -> str:
    data: List[str] = [f"[$RootKey$\\Themes\\{{{theme.guid}}}]"]
    data.append(f'@="{theme.name}"')
    data.append(f'"Name"="{theme.name}"')
    data.append(f'"Package"="{{{theme.guid}}}"')
    data.append(f'"FallbackId"="{{{theme.base_guid}}}"')

    for name, entries in sections.items():
        data.append(build_section(theme.guid, name, entries))
    return "\n".join(data).strip()

def content_types_xml_data() -> str:
    return f"""
<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="vsixmanifest" ContentType="text/xml" />
  <Default Extension="pkgdef" ContentType="text/plain" />
  <Default Extension="png" ContentType="application/octet-stream" />
  <Default Extension="json" ContentType="application/json" />
</Types>
    """.strip()

def vsixmanifest_data(theme: Any) -> str:
    return f"""
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Id="{theme.id}" Version="{theme.version}" Language="en-US" Publisher="{theme.author}" />
    <DisplayName>{theme.name}</DisplayName>
    <Description xml:space="preserve">{theme.description}</Description>
    {f"<Icon>{theme.icon}</Icon>" if theme.icon else ""}
    <Tags>{theme.tags}</Tags>
  </Metadata>
  <Installation AllUsers="true">
    <InstallationTarget Version="{theme.target_version}" Id="Microsoft.VisualStudio.Community"><ProductArchitecture>amd64</ProductArchitecture></InstallationTarget>
    <InstallationTarget Version="{theme.target_version}" Id="Microsoft.VisualStudio.Community"><ProductArchitecture>arm64</ProductArchitecture></InstallationTarget>
    <InstallationTarget Version="{theme.target_version}" Id="Microsoft.VisualStudio.Enterprise"><ProductArchitecture>amd64</ProductArchitecture></InstallationTarget>
    <InstallationTarget Version="{theme.target_version}" Id="Microsoft.VisualStudio.Enterprise"><ProductArchitecture>arm64</ProductArchitecture></InstallationTarget>
    <InstallationTarget Version="{theme.target_version}" Id="Microsoft.VisualStudio.Pro"><ProductArchitecture>amd64</ProductArchitecture></InstallationTarget>
    <InstallationTarget Version="{theme.target_version}" Id="Microsoft.VisualStudio.Pro"><ProductArchitecture>arm64</ProductArchitecture></InstallationTarget>
  </Installation>
  <Dependencies><Dependency Id="Microsoft.Framework.NDP" DisplayName="Microsoft .NET Framework" Version="[4.5,)" /></Dependencies>
  <Prerequisites><Prerequisite Id="Microsoft.VisualStudio.Component.CoreEditor" Version="{theme.target_version}" DisplayName="Visual Studio core editor" /></Prerequisites>
  <Assets><Asset Type="Microsoft.VisualStudio.ColorTheme" Path="extension.pkgdef" /></Assets>
</PackageManifest>
    """.strip()

def catalog_json_data(theme: Any) -> str:
    return f"""{{ "manifestVersion": "1.1", "info": {{ "id": "{theme.id},version={theme.version}", "manifestType": "Extension" }}, "packages": [{{ "id": "Component.{theme.id}", "version": "{theme.version}", "type": "Component", "extension": true, "dependencies": {{ "{theme.id}": "{theme.version}", "Microsoft.VisualStudio.Component.CoreEditor": "{theme.target_version}" }}, "localizedResources": [{{ "language": "en-US", "title": "{theme.name}", "description": "{theme.description}" }}] }}, {{ "id": "{theme.id}", "version": "{theme.version}", "type": "Vsix", "vsixId": "{theme.id}", "extensionDir": "{theme.extension_dir}", "payloads": [{{ "fileName": "{os.path.basename(theme.vsix_file)}" }}] }}] }}"""

def manifest_json_data(theme: Any) -> str:
    return f"""{{ "id": "{theme.id}", "version": "{theme.version}", "type": "Vsix", "vsixId": "{theme.id}", "extensionDir": "{theme.extension_dir}", "dependencies": {{ "Microsoft.VisualStudio.Component.CoreEditor": "{theme.target_version}" }}, "files": [{{ "fileName": "/extension.vsixmanifest", "sha256": null }}, {{ "fileName": "/extension.pkgdef", "sha256": null }} {f', {{ "fileName": "/{theme.icon}", "sha256": null }}' if theme.icon else ""}] }}"""

def get_elem(config: Dict[str, Any], key: str) -> Any:
    if key not in config:
        raise ValueError(f"Input config must have a '{key}' field")
    return config[key]

def get_random_ext_dir(guid: str) -> str:
    dir_name = guid[::-1][0:8] + '.' + guid[::-1][8:11]
    return f"[installdir]\\\\Common7\\\\IDE\\\\Extensions\\\\{dir_name}"

def main() -> int:
    ap = argparse.ArgumentParser(description="Build VS theme from YAML config file")
    ap.add_argument("-i", "--input", required=True, help="YAML config file")
    ap.add_argument("-o", "--output", required=True, help="VSIX theme file name")
    args = ap.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    theme = SimpleNamespace(
        name = get_elem(config, "Name"),
        identity = get_elem(config, "Identity"),
        guid = "-".join(guid_parts(get_elem(config, "GUID"))),
        base_guid = "-".join(guid_parts(get_elem(config, "BaseGUID"))),
        version = get_elem(config, "Version"),
        author = config.get("Author", "Unknown"),
        description = config.get("Description", ""),
        tags = config.get("Tags", ""),
        icon = config.get("Icon", None),
        target_version = "[17.0,19.0)",
        vsix_file = args.output + ".vsix"
    )
    theme.id = f"{theme.author.replace(' ', '-')}.{theme.identity}"
    theme.extension_dir = get_random_ext_dir(theme.guid)
    
    with tempfile.TemporaryDirectory(dir='.') as tmp_dir:
        files: List[Path] = []
        work_dir = Path(tmp_dir)
        if theme.icon:
            icon_path = Path(theme.icon)
            if icon_path.exists():
                file = work_dir / icon_path.name
                shutil.copy(icon_path, file)
                theme.icon = icon_path.name
                files.append(file)
            else:
                print(f"'{theme.icon}' doesn't exist! building without icon.")
                theme.icon = None
        
        file = work_dir / "extension.pkgdef"
        file.write_text(pkgdef_data(theme, get_elem(config, "Sections")), encoding="utf-8")
        files.append(file)
        
        file = work_dir / "[Content_Types].xml"
        file.write_text(content_types_xml_data(), encoding="utf-8")
        files.append(file)

        file = work_dir / "extension.vsixmanifest"
        file.write_text(vsixmanifest_data(theme), encoding="utf-8")
        files.append(file)

        file = work_dir / "catalog.json"
        file.write_text(catalog_json_data(theme), encoding="utf-8")
        files.append(file)

        file = work_dir / "manifest.json"
        file.write_text(manifest_json_data(theme), encoding="utf-8")
        files.append(file)

        with zipfile.ZipFile(theme.vsix_file, "w", compression=zipfile.ZIP_DEFLATED) as zip:
            for file in files:
                zip.write(file, os.path.basename(file))
            print(f"'{theme.vsix_file}' build complete.")

    return 0

if __name__ == "__main__":
    exit(main())