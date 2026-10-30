#include "FleetCameraPawn.h"

#include "Camera/CameraComponent.h"
#include "FleetEnvironment.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/HUD.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "UnrealClient.h"

namespace
{
	struct FPresentationShot
	{
		EFleetShipType Type;
		int32 Kind;
		const TCHAR* Label;
	};

	const FPresentationShot Shots[] = {
		{ EFleetShipType::Container, 0, TEXT("ThreeQuarter") },
		{ EFleetShipType::Container, 1, TEXT("Profile") },
		{ EFleetShipType::Container, 4, TEXT("Sea") },
		{ EFleetShipType::Container, 3, TEXT("BowWaterline") },
		{ EFleetShipType::Container, 5, TEXT("Wake") },
		{ EFleetShipType::Container, 2, TEXT("Overview") },
		{ EFleetShipType::Container, 7, TEXT("Horizon") },
		{ EFleetShipType::Container, 6, TEXT("RoughSea") },
		{ EFleetShipType::Container, 8, TEXT("SpringTide") },
		{ EFleetShipType::Container, 8, TEXT("AutumnGale") },
		{ EFleetShipType::Container, 8, TEXT("WinterStorm") }
	};
}

AFleetCameraPawn::AFleetCameraPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	SetRootComponent(Camera);
	Camera->SetFieldOfView(72.f);
}

void AFleetCameraPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bPresentationClockStarted)
	{
		bPresentationShots = FParse::Param(FCommandLine::Get(), TEXT("ShipShots"));
		bPresentationClockStarted = true;
	}
	if (bPresentationShots)
	{
		TickPresentationShots(FPlatformTime::Seconds());
		return;
	}
	TickFleetView();
}

void AFleetCameraPawn::TickFleetView()
{
	FVector Center = FVector::ZeroVector;
	FVector Heading = FVector::ZeroVector;
	int32 Count = 0;
	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		Center += It->GetActorLocation();
		Heading += FRotator(0.f, It->GetHeadingDegrees(), 0.f).Vector();
		++Count;
	}
	if (Count == 0)
	{
		return;
	}

	Center /= Count;
	float Radius = 0.f;
	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		Radius = FMath::Max(Radius, FVector::Dist2D(It->GetActorLocation(), Center));
	}
	const float Back = FMath::Clamp(24000.f + Radius * 1.2f, 34000.f, 140000.f);
	const float Up = FMath::Clamp(Back * 0.19f, 7500.f, 28000.f);
	const FVector Forward = Heading.GetSafeNormal();
	const FVector CameraLocation = FVector(Center.X, Center.Y, 0.f) - Forward * Back + FVector(0.f, 0.f, Up);
	const FVector LookAt(Center.X, Center.Y, 250.f);
	Camera->SetFieldOfView(72.f);
	SetActorLocation(CameraLocation);
	SetActorRotation((LookAt - CameraLocation).Rotation());
}

AFleetShip* AFleetCameraPawn::FindShip(EFleetShipType Type) const
{
	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		if (It->GetShipType() == Type)
		{
			return *It;
		}
	}
	return nullptr;
}

void AFleetCameraPawn::FrameShip(const AFleetShip& Ship, int32 Kind)
{
	const float Length = Ship.GetLengthCm();
	const float Beam = Ship.GetBeamCm();
	FVector LocalCamera;
	FVector LocalLook = FVector::ZeroVector;
	float FieldOfView = 42.f;
	switch (Kind)
	{
	case 1:
		LocalCamera = FVector(0.f, Length * 1.25f, 1800.f);
		LocalLook = FVector(0.f, 0.f, -280.f);
		FieldOfView = 52.f;
		break;
	case 2:
		LocalCamera = FVector(-Length * 0.35f, Length * 0.72f, Length * 0.38f);
		LocalLook = FVector(Length * 0.08f, 0.f, -200.f);
		FieldOfView = 58.f;
		break;
	case 3:
		LocalCamera = FVector(Length * 0.68f, Beam * 1.55f, 620.f);
		LocalLook = FVector(Length * 0.40f, 0.f, -30.f);
		FieldOfView = 50.f;
		break;
	case 4:
	case 6:
		LocalCamera = FVector(Length * 0.18f, FMath::Max(Beam * 2.6f, 11000.f), 780.f);
		LocalLook = FVector(Length * 0.02f, 0.f, -60.f);
		FieldOfView = 64.f;
		break;
	case 5:
		LocalCamera = FVector(-Length * 0.22f, Beam * 1.7f, 720.f);
		LocalLook = FVector(-Length * 0.58f, 0.f, -20.f);
		FieldOfView = 52.f;
		break;
	case 7:
	case 8:
		LocalCamera = FVector(-Length * 0.05f, -FMath::Max(Beam * 3.4f, 14000.f), 1100.f);
		LocalLook = FVector(Length * 0.55f, 0.f, -80.f);
		FieldOfView = 68.f;
		break;
	default:
		LocalCamera = FVector(Length * 0.48f, Length * 0.34f, 2400.f);
		LocalLook = FVector(Length * 0.08f, 0.f, -180.f);
		FieldOfView = 48.f;
		break;
	}
	const FTransform ShipTransform = Ship.GetActorTransform();
	const FVector CameraLocation = ShipTransform.TransformPosition(LocalCamera);
	const FVector LookAt = ShipTransform.TransformPosition(LocalLook);
	Camera->SetFieldOfView(FieldOfView);
	SetActorLocation(CameraLocation);
	SetActorRotation((LookAt - CameraLocation).Rotation());
}

void AFleetCameraPawn::CaptureShot(const AFleetShip& Ship, const TCHAR* Label)
{
	if (APlayerController* Controller = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr)
	{
		if (AHUD* Hud = Controller->GetHUD())
		{
			Hud->bShowHUD = false;
		}
	}
	const FString Directory = FPaths::ProjectSavedDir() / TEXT("Screenshots/VesselPresentation");
	IFileManager::Get().MakeDirectory(*Directory, true);
	const FString ShipToken = Ship.GetShipName().Replace(TEXT(" "), TEXT("_"));
	const FString Filename = Directory / FString::Printf(TEXT("%s_%s.png"), *ShipToken, Label);
	FScreenshotRequest::RequestScreenshot(Filename, false, true);
	UE_LOG(LogTemp, Display, TEXT("SHIPSHOT %s %s -> %s"), *Ship.GetShipName(), Label, *Filename);
}

void AFleetCameraPawn::TickPresentationShots(double NowSeconds)
{
	constexpr int32 ShotCount = UE_ARRAY_COUNT(Shots);
	if (PresentationLeadFrames < 240)
	{
		++PresentationLeadFrames;
		TickFleetView();
		return;
	}
	if (PresentationShot >= ShotCount)
	{
		++FramesAfterLastShot;
		if (FramesAfterLastShot > 30 && PresentationCaptures >= ShotCount)
		{
			UE_LOG(LogTemp, Display, TEXT("SHIPSHOT COMPLETE %d"), PresentationCaptures);
			FPlatformMisc::RequestExit(false);
		}
		return;
	}

	const FPresentationShot& Shot = Shots[PresentationShot];
	if (AFleetShip* Ship = FindShip(Shot.Type))
	{
		if (PresentationFrames == 0 && (Shot.Kind == 6 || Shot.Kind == 8))
		{
			TActorIterator<AFleetEnvironment> EnvIt(GetWorld());
			if (AFleetEnvironment* Environment = EnvIt ? *EnvIt : nullptr)
			{
				if (Shot.Kind == 6)
				{
					Environment->SetVisualSea(2);
				}
				else if (FCString::Strcmp(Shot.Label, TEXT("SpringTide")) == 0)
				{
					Environment->SetVisualSea(1);
					Environment->ApplyPreset(1);
				}
				else if (FCString::Strcmp(Shot.Label, TEXT("AutumnGale")) == 0)
				{
					Environment->SetVisualSea(1);
					Environment->ApplyPreset(2);
				}
				else if (FCString::Strcmp(Shot.Label, TEXT("WinterStorm")) == 0)
				{
					Environment->SetVisualSea(1);
					Environment->ApplyPreset(3);
				}
			}
		}
		FrameShip(*Ship, Shot.Kind);
		++PresentationFrames;
		if (PresentationFrames == 20)
		{
			CaptureShot(*Ship, Shot.Label);
			++PresentationCaptures;
		}
		if (PresentationFrames > 28)
		{
			++PresentationShot;
			PresentationFrames = 0;
		}
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("SHIPSHOT missing ship for %s"), Shot.Label);
		++PresentationShot;
		PresentationFrames = 0;
	}
	(void)NowSeconds;
}
