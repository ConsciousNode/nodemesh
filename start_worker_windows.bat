@echo off
REM NodeMesh Worker Agent Startup Script
REM For: Windows 11 (Laptop - lightweight tasks)
REM This registers the Windows laptop as a worker node in the mesh

setlocal EnableDelayedExpansion

echo ===============================================
echo   NodeMesh Worker (Windows 11)
echo ===============================================
echo.

REM Configuration - UPDATE THESE FOR YOUR SETUP
set "NODE_NAME=windows-laptop"
set "COORDINATOR_URL=http://192.168.1.100:11434"
set "MODELS_DIR=%USERPROFILE%\GGUF-Models"
set "WORKER_PORT=11436"
set "LLAMA_PORT=11437"

echo Configuration:
echo   Node Name: %NODE_NAME%
echo   Coordinator: %COORDINATOR_URL%
echo   Models Dir: %MODELS_DIR%
echo   Worker Port: %WORKER_PORT%
echo   Llama.cpp Port: %LLAMA_PORT%
echo.

REM Get script directory
set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."
set "WORKER_DIR=%PROJECT_DIR%\worker"

REM Check hardware
echo Checking hardware...
for /f "skip=1" %%p in ('wmic computersystem get TotalPhysicalMemory') do (
    set "TOTAL_RAM=%%p"
    goto :ram_done
)
:ram_done
for /f "skip=1" %%p in ('wmic cpu get NumberOfLogicalProcessors') do (
    set "CPU_CORES=%%p"
    goto :cpu_done
)
:cpu_done

REM Convert bytes to MB (rough)
set /a "TOTAL_RAM_MB=%TOTAL_RAM:~0,-6%"
echo   RAM: %TOTAL_RAM_MB% MB
echo   CPU Cores: %CPU_CORES%
echo.

if %TOTAL_RAM_MB% LSS 4096 (
    echo NOTE: Limited RAM detected. Only small models (1B-3B) recommended.
    echo Consider using Q2 or Q3 quantization for better performance.
    echo.
)

cd /d "%WORKER_DIR%"

REM Setup Python environment
if not exist "venv" (
    echo Creating Python virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -q --upgrade pip
pip install -q -r requirements.txt

REM Check for llama.cpp server
echo.
echo Checking for llama-server.exe...
where llama-server.exe >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   llama-server.exe not found in PATH
    echo.
    echo Please build llama.cpp from source:
    echo   1. Install Visual Studio 2022 with C++ workload
    echo   2. git clone https://github.com/ggerganov/llama.cpp
    echo   3. cd llama.cpp
    echo   4. cmake -B build
    echo   5. cmake --build build --config Release -j4
    echo   6. Add buildinelease to your PATH
    echo.
    echo Or download pre-built binaries from:
    echo   https://github.com/ggerganov/llama.cpp/releases
    pause
    exit /b 1
) else (
    for /f "tokens=*" %%p in ('where llama-server.exe') do (
        echo   Found: %%p
    )
)

REM Check for models directory
if not exist "%MODELS_DIR%" (
    echo.
    echo WARNING: Models directory not found: %MODELS_DIR%
    echo Creating directory...
    mkdir "%MODELS_DIR%"
    echo.
    echo Please download small GGUF models suitable for this hardware:
    echo   - Phi-3 Mini (3.8B) Q4_K_M: ~2.3GB
    echo   - Qwen2.5 1.5B Q4: ~1GB
    echo   - TinyLlama 1.1B Q4: ~0.6GB
    echo.
    echo Download from: https://huggingface.co/models?search=gguf
    pause
)

echo.
echo Starting NodeMesh Worker...
echo This node will register with: %COORDINATOR_URL%
echo.
echo Press Ctrl+C to stop
echo ===============================================
echo.

REM Run the worker
python agent.py ^
    --name %NODE_NAME% ^
    --coordinator %COORDINATOR_URL% ^
    --models-dir "%MODELS_DIR%" ^
    --port %WORKER_PORT% ^
    --llama-port %LLAMA_PORT%

pause
