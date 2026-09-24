@echo off
rem Rebuilds braw_decode.exe against the Blackmagic RAW SDK headers.
rem Usage: build_braw_decode.bat "C:\path\to\Blackmagic RAW SDK\Win\Include"
setlocal
set "SDKINC=%~1"
if "%SDKINC%"=="" (
    echo Usage: build_braw_decode.bat "path\to\Blackmagic RAW SDK\Win\Include"
    exit /b 2
)
if not exist "%SDKINC%\BlackmagicRawAPI.idl" (
    echo BlackmagicRawAPI.idl not found in "%SDKINC%"
    exit /b 2
)
cd /d "%~dp0" || exit /b 2
if not exist Generated mkdir Generated
set "VCVARS=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VCVARS%" (
    echo vcvars64.bat not found: install the Visual Studio Build Tools with the C++ workload.
    exit /b 2
)
call "%VCVARS%" >nul || exit /b 2
midl /nologo /env x64 /I "%SDKINC%" /h Generated\BlackmagicRawAPI.h /iid Generated\BlackmagicRawAPI_i.c /tlb Generated\BlackmagicRawAPI.tlb "%SDKINC%\BlackmagicRawAPI.idl" || exit /b 1
cl /nologo /std:c++17 /O2 /EHsc /DUNICODE /D_UNICODE /I Generated /I "%SDKINC%" braw_decode.cpp "%SDKINC%\BlackmagicRawAPIDispatch.cpp" Generated\BlackmagicRawAPI_i.c /Fe:braw_decode.exe /link ole32.lib oleaut32.lib || exit /b 1
del /q *.obj >nul 2>&1
rem Keep the local dev copy in portable/bin in sync (gitignored, but stale copies lie).
if exist "..\..\portable\bin" copy /y braw_decode.exe "..\..\portable\bin\braw_decode.exe" >nul
echo Built braw_decode.exe against "%SDKINC%"
