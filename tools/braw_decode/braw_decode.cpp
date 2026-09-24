// Minimal Blackmagic RAW decoder for the portable proxy pipeline.
// Uses the official Blackmagic RAW SDK and writes RGBA frames to stdout.

#include "BlackmagicRawAPIDispatch.h"

#include <fcntl.h>
#include <io.h>
#include <windows.h>

#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <mutex>
#include <string>
#include <vector>

static BlackmagicRawResolutionScale g_scale = blackmagicRawResolutionScaleQuarter;
static const BlackmagicRawResourceFormat g_resourceFormat = blackmagicRawResourceFormatRGBAU16;
static const size_t g_bytesPerPixel = 8u;

struct FrameResult
{
	std::mutex mutex;
	std::condition_variable cv;
	bool done = false;
	HRESULT result = S_OK;
	unsigned int width = 0;
	unsigned int height = 0;
	std::vector<uint8_t> pixels;
};

static std::wstring Utf8ToWide(const char* value)
{
	int len = MultiByteToWideChar(CP_UTF8, 0, value, -1, nullptr, 0);
	if (len <= 0)
		len = MultiByteToWideChar(CP_ACP, 0, value, -1, nullptr, 0);
	std::wstring wide((size_t)len, L'\0');
	MultiByteToWideChar(CP_UTF8, 0, value, -1, wide.data(), len);
	if (!wide.empty() && wide.back() == L'\0')
		wide.pop_back();
	return wide;
}

static std::string WideToUtf8(const BSTR value)
{
	if (value == nullptr)
		return "";
	int len = WideCharToMultiByte(CP_UTF8, 0, value, SysStringLen(value), nullptr, 0, nullptr, nullptr);
	std::string out((size_t)len, '\0');
	WideCharToMultiByte(CP_UTF8, 0, value, SysStringLen(value), out.data(), len, nullptr, nullptr);
	return out;
}

static BlackmagicRawResolutionScale ParseScale(const char* value)
{
	if (strcmp(value, "1") == 0)
		return blackmagicRawResolutionScaleFull;
	if (strcmp(value, "2") == 0)
		return blackmagicRawResolutionScaleHalf;
	if (strcmp(value, "4") == 0)
		return blackmagicRawResolutionScaleQuarter;
	if (strcmp(value, "8") == 0)
		return blackmagicRawResolutionScaleEighth;
	std::cerr << "Invalid scale. Use 1, 2, 4, or 8." << std::endl;
	exit(2);
}

class DecodeCallback : public IBlackmagicRawCallback
{
public:
	void ReadComplete(IBlackmagicRawJob* readJob, HRESULT result, IBlackmagicRawFrame* frame) override
	{
		FrameResult* frameResult = nullptr;
		readJob->GetUserData(reinterpret_cast<void**>(&frameResult));

		IBlackmagicRawJob* decodeJob = nullptr;
		if (SUCCEEDED(result))
			result = frame->SetResourceFormat(g_resourceFormat);
		if (SUCCEEDED(result))
			result = frame->SetResolutionScale(g_scale);
		if (SUCCEEDED(result))
			result = frame->CreateJobDecodeAndProcessFrame(nullptr, nullptr, &decodeJob);
		if (SUCCEEDED(result))
		{
			decodeJob->SetUserData(frameResult);
			result = decodeJob->Submit();
		}

		if (FAILED(result))
		{
			if (decodeJob != nullptr)
				decodeJob->Release();
			Signal(frameResult, result);
		}
		readJob->Release();
	}

	void ReadAudioComplete(IBlackmagicRawJob*, HRESULT, IBlackmagicRawAudioBuffer*) override {}

	void ProcessComplete(IBlackmagicRawJob* job, HRESULT result, IBlackmagicRawProcessedImage* processedImage) override
	{
		FrameResult* frameResult = nullptr;
		job->GetUserData(reinterpret_cast<void**>(&frameResult));

		unsigned int width = 0;
		unsigned int height = 0;
		void* imageData = nullptr;

		if (SUCCEEDED(result))
			result = processedImage->GetWidth(&width);
		if (SUCCEEDED(result))
			result = processedImage->GetHeight(&height);
		if (SUCCEEDED(result))
			result = processedImage->GetResource(&imageData);
		if (SUCCEEDED(result))
		{
			const size_t byteCount = (size_t)width * (size_t)height * g_bytesPerPixel;
			frameResult->width = width;
			frameResult->height = height;
			frameResult->pixels.assign(static_cast<uint8_t*>(imageData), static_cast<uint8_t*>(imageData) + byteCount);
		}

		job->Release();
		Signal(frameResult, result);
	}

	void DecodeComplete(IBlackmagicRawJob*, HRESULT) override {}
	void TrimProgress(IBlackmagicRawJob*, float) override {}
	void TrimComplete(IBlackmagicRawJob*, HRESULT) override {}
	void SidecarMetadataParseWarning(IBlackmagicRawClip*, BSTR, uint32_t, BSTR) override {}
	void SidecarMetadataParseError(IBlackmagicRawClip*, BSTR, uint32_t, BSTR) override {}
	void PreparePipelineComplete(void*, HRESULT) override {}

	HRESULT STDMETHODCALLTYPE QueryInterface(REFIID, LPVOID*) override { return E_NOTIMPL; }
	ULONG STDMETHODCALLTYPE AddRef(void) override { return 1; }
	ULONG STDMETHODCALLTYPE Release(void) override { return 1; }

private:
	void Signal(FrameResult* frameResult, HRESULT result)
	{
		if (frameResult == nullptr)
			return;
		{
			std::lock_guard<std::mutex> lock(frameResult->mutex);
			frameResult->result = result;
			frameResult->done = true;
		}
		frameResult->cv.notify_one();
	}
};

static bool DecodeFrame(IBlackmagicRawClip* clip, IBlackmagicRaw* codec, unsigned long long frameIndex, FrameResult& frameResult)
{
	frameResult.done = false;
	frameResult.result = S_OK;
	frameResult.pixels.clear();

	IBlackmagicRawJob* readJob = nullptr;
	HRESULT result = clip->CreateJobReadFrame(frameIndex, &readJob);
	if (FAILED(result))
	{
		std::cerr << "Failed to create read job for frame " << frameIndex
			<< ". The imported Blackmagic RAW SDK is older than this decoder expects." << std::endl;
		return false;
	}

	IBlackmagicRawReadJobHints* readHints = nullptr;
	if (SUCCEEDED(readJob->QueryInterface(IID_IBlackmagicRawReadJobHints, reinterpret_cast<void**>(&readHints))))
	{
		readHints->SetReaderResolutionScale(g_scale);
		readHints->Release();
	}

	readJob->SetUserData(&frameResult);
	result = readJob->Submit();
	if (FAILED(result))
	{
		readJob->Release();
		std::cerr << "Failed to submit read job for frame " << frameIndex << std::endl;
		return false;
	}

	std::unique_lock<std::mutex> lock(frameResult.mutex);
	frameResult.cv.wait(lock, [&frameResult] { return frameResult.done; });
	lock.unlock();
	codec->FlushJobs();

	if (FAILED(frameResult.result))
	{
		std::cerr << "Failed to decode frame " << frameIndex << " HRESULT=0x" << std::hex << frameResult.result << std::dec << std::endl;
		return false;
	}
	return true;
}

static void PrintUsage()
{
	std::cerr << "Usage:\n"
		<< "  braw_decode --info --sdk <sdk_folder> [--scale 4] <clip.braw>\n"
		<< "  braw_decode --raw  --sdk <sdk_folder> [--scale 4] <clip.braw>\n";
}

int main(int argc, const char* argv[])
{
	bool infoMode = false;
	bool rawMode = false;
	const char* sdkPathArg = nullptr;
	const char* clipPathArg = nullptr;

	for (int i = 1; i < argc; ++i)
	{
		if (strcmp(argv[i], "--info") == 0)
			infoMode = true;
		else if (strcmp(argv[i], "--raw") == 0)
			rawMode = true;
		else if (strcmp(argv[i], "--sdk") == 0 && i + 1 < argc)
			sdkPathArg = argv[++i];
		else if (strcmp(argv[i], "--scale") == 0 && i + 1 < argc)
			g_scale = ParseScale(argv[++i]);
		else if (argv[i][0] != '-')
			clipPathArg = argv[i];
		else
		{
			PrintUsage();
			return 2;
		}
	}

	if ((infoMode == rawMode) || sdkPathArg == nullptr || clipPathArg == nullptr)
	{
		PrintUsage();
		return 2;
	}

	if (rawMode)
		_setmode(_fileno(stdout), _O_BINARY);

	HRESULT result = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
	if (FAILED(result))
	{
		std::cerr << "COM initialization failed." << std::endl;
		return 1;
	}

	IBlackmagicRawFactory* factory = nullptr;
	IBlackmagicRaw* codec = nullptr;
	IBlackmagicRawClip* clip = nullptr;
	DecodeCallback callback;
	int exitCode = 1;

	BSTR sdkPath = SysAllocString(Utf8ToWide(sdkPathArg).c_str());
	BSTR clipPath = SysAllocString(Utf8ToWide(clipPathArg).c_str());

	do
	{
		factory = CreateBlackmagicRawFactoryInstanceFromPath(sdkPath);
		if (factory == nullptr)
		{
			std::cerr << "Failed to create Blackmagic RAW factory from SDK path." << std::endl;
			break;
		}

		result = factory->CreateCodec(&codec);
		if (FAILED(result))
		{
			std::cerr << "Failed to create Blackmagic RAW codec." << std::endl;
			break;
		}

		result = codec->OpenClip(clipPath, &clip);
		if (FAILED(result))
		{
			std::cerr << "Failed to open BRAW clip." << std::endl;
			break;
		}

		unsigned long long frameCount = 0;
		float frameRate = 0.0f;
		unsigned int width = 0;
		unsigned int height = 0;
		BSTR timecode = nullptr;

		clip->GetFrameCount(&frameCount);
		clip->GetFrameRate(&frameRate);
		IBlackmagicRawClipResolutions* resolutions = nullptr;
		if (SUCCEEDED(clip->QueryInterface(IID_IBlackmagicRawClipResolutions, reinterpret_cast<void**>(&resolutions))))
		{
			resolutions->GetClosestResolutionForScale(g_scale, &width, &height);
			resolutions->Release();
		}
		clip->GetTimecodeForFrame(0, &timecode);

		if (infoMode)
		{
			std::cout << "{"
				<< "\"width\":" << width << ","
				<< "\"height\":" << height << ","
				<< "\"frame_rate\":" << frameRate << ","
				<< "\"frame_count\":" << frameCount << ","
				<< "\"timecode\":\"" << WideToUtf8(timecode) << "\""
				<< "}" << std::endl;
			exitCode = 0;
			if (timecode != nullptr)
				SysFreeString(timecode);
			break;
		}

		if (timecode != nullptr)
			SysFreeString(timecode);

		result = codec->SetCallback(&callback);
		if (FAILED(result))
		{
			std::cerr << "Failed to set decoder callback. A newer Blackmagic RAW SDK is required." << std::endl;
			break;
		}

		FrameResult frameResult;
		for (unsigned long long frame = 0; frame < frameCount; ++frame)
		{
			if (!DecodeFrame(clip, codec, frame, frameResult))
				break;
			if (frameResult.width != width || frameResult.height != height)
			{
				std::cerr << "Decoded dimensions changed unexpectedly." << std::endl;
				break;
			}
			const size_t written = fwrite(frameResult.pixels.data(), 1, frameResult.pixels.size(), stdout);
			if (written != frameResult.pixels.size())
			{
				std::cerr << "Failed to write frame to stdout." << std::endl;
				break;
			}
			if (frame + 1 == frameCount)
				exitCode = 0;
		}
		fflush(stdout);
	} while (0);

	if (clip != nullptr)
		clip->Release();
	if (codec != nullptr)
		codec->Release();
	if (factory != nullptr)
		factory->Release();

	SysFreeString(sdkPath);
	SysFreeString(clipPath);
	CoUninitialize();
	return exitCode;
}
