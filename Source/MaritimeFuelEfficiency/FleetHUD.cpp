#include "FleetHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "EngineUtils.h"
#include "FleetEnvironment.h"
#include "FleetShip.h"

namespace
{
	FLinearColor ShipColor(EFleetShipType Type)
	{
		if (Type == EFleetShipType::Tanker)
		{
			return FLinearColor(1.f, 0.55f, 0.45f);
		}
		if (Type == EFleetShipType::Bulker)
		{
			return FLinearColor(0.55f, 0.95f, 0.55f);
		}
		return FLinearColor(0.65f, 0.82f, 1.f);
	}

	float Heading360(float Degrees)
	{
		return FMath::Fmod(Degrees + 360.f, 360.f);
	}
}

void AFleetHUD::DrawWorldLine(const FVector& Start, const FVector& End, const FLinearColor& Color)
{
	if (!Canvas)
	{
		return;
	}
	const FVector ProjectedStart = Canvas->Project(Start, false);
	const FVector ProjectedEnd = Canvas->Project(End, false);
	if (ProjectedStart.Z <= 0.f || ProjectedEnd.Z <= 0.f)
	{
		return;
	}
	DrawLine(ProjectedStart.X, ProjectedStart.Y, ProjectedEnd.X, ProjectedEnd.Y, Color, 2.5f);
}

void AFleetHUD::DrawCommand(float X, float Y, float W, float H, const FString& Label, FName BoxName)
{
	DrawRect(FLinearColor(0.05f, 0.08f, 0.12f, 0.88f), X, Y, W, H);
	DrawRect(FLinearColor(0.45f, 0.62f, 0.78f, 1.f), X, Y, W, 1.f);
	if (GEngine)
	{
		DrawText(Label, FLinearColor(0.9f, 0.94f, 0.97f), X + 6.f, Y + 3.f, GEngine->GetMediumFont(), 0.62f);
	}
	AddHitBox(FVector2D(X, Y), FVector2D(W, H), BoxName, true, 0);
}

void AFleetHUD::NotifyHitBoxClick(FName BoxName)
{
	TActorIterator<AFleetEnvironment> EnvIt(GetWorld());
	AFleetEnvironment* Environment = EnvIt ? *EnvIt : nullptr;
	if (!Environment)
	{
		return;
	}
	if (BoxName == TEXT("Season0")) Environment->ApplyPreset(0);
	else if (BoxName == TEXT("Season1")) Environment->ApplyPreset(1);
	else if (BoxName == TEXT("Season2")) Environment->ApplyPreset(2);
	else if (BoxName == TEXT("Season3")) Environment->ApplyPreset(3);
	else if (BoxName == TEXT("WindUp")) Environment->NudgeWindSpeed(1.f);
	else if (BoxName == TEXT("WindDn")) Environment->NudgeWindSpeed(-1.f);
	else if (BoxName == TEXT("WindL")) Environment->NudgeWindDirection(-10.f);
	else if (BoxName == TEXT("WindR")) Environment->NudgeWindDirection(10.f);
	else if (BoxName == TEXT("CurUp")) Environment->NudgeCurrentSpeed(0.2f);
	else if (BoxName == TEXT("CurDn")) Environment->NudgeCurrentSpeed(-0.2f);
	else if (BoxName == TEXT("CurL")) Environment->NudgeCurrentDirection(-10.f);
	else if (BoxName == TEXT("CurR")) Environment->NudgeCurrentDirection(10.f);
	else if (BoxName == TEXT("WaveUp")) Environment->NudgeWaveHeight(0.4f);
	else if (BoxName == TEXT("WaveDn")) Environment->NudgeWaveHeight(-0.4f);
	else if (BoxName == TEXT("WaveL")) Environment->NudgeWaveDirection(-10.f);
	else if (BoxName == TEXT("WaveR")) Environment->NudgeWaveDirection(10.f);
	else if (BoxName == TEXT("Time1")) Environment->SetTimeScale(1.f);
	else if (BoxName == TEXT("Time5")) Environment->SetTimeScale(5.f);
	else if (BoxName == TEXT("Time10")) Environment->SetTimeScale(10.f);
	else if (BoxName == TEXT("Time20")) Environment->SetTimeScale(20.f);
	else if (BoxName == TEXT("Pause")) Environment->TogglePause();
	else if (BoxName == TEXT("Reset")) Environment->ResetSimulation();
}

void AFleetHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas || !GEngine)
	{
		return;
	}

	UFont* Font = GEngine->GetMediumFont();
	const float Scale = 0.9f;
	float Y = 12.f;
	TActorIterator<AFleetEnvironment> EnvIt(GetWorld());
	const AFleetEnvironment* Environment = EnvIt ? *EnvIt : nullptr;
	if (Environment)
	{
		const int32 WholeHour = FMath::FloorToInt(Environment->GetHour());
		const int32 Minute = FMath::FloorToInt((Environment->GetHour() - WholeHour) * 60.f);
		const FString Title = FString::Printf(TEXT("%s    %s    %.0fx    %02d:%02d    %s"),
			*Environment->GetPresetName().ToUpper(),
			Environment->IsPaused() ? TEXT("PAUSED") : TEXT("RUNNING"),
			Environment->GetTimeScale(),
			WholeHour,
			Minute,
			Environment->IsPhysicsConnected() ? TEXT("MMG physics") : TEXT("physics waiting"));
		DrawText(Title, FLinearColor(1.f, 0.92f, 0.45f), 16.f, Y, Font, 1.05f);
		Y += 26.f;
		const FString Sea = FString::Printf(TEXT("wind %.1f m/s at %.0f    current %.2f m/s at %.0f    waves %.1f m at %.0f    %s%s"),
			Environment->GetWindSpeedMs(),
			Environment->GetWindDirectionDeg(),
			Environment->GetCurrentSpeedMs(),
			Environment->GetCurrentDirectionDeg(),
			Environment->GetWaveHeightM(),
			Environment->GetWaveDirectionDeg(),
			*Environment->GetVisualSeaName(),
			Environment->IsDayNightCycle() ? TEXT("    day/night cycle") : TEXT(""));
		DrawText(Sea, FLinearColor::White, 16.f, Y, Font, Scale);
		Y += 22.f;
		DrawText(TEXT("1 5 0 2 time    Space pause    Enter run    Bksp reset    Z X C V seasons    arrows wind    I K J L current    U O Y H waves    T G hour    N cycle"), FLinearColor(0.75f, 0.82f, 0.9f), 16.f, Y, Font, 0.62f);
		Y += 18.f;

		const float PanelX = Canvas->SizeX - 348.f;
		float PanelY = 12.f;
		DrawRect(FLinearColor(0.02f, 0.04f, 0.07f, 0.82f), PanelX - 8.f, 8.f, 340.f, 470.f);
		DrawText(TEXT("MMG CONTROLS"), FLinearColor(1.f, 0.92f, 0.45f), PanelX, PanelY, Font, 0.85f);
		PanelY += 24.f;
		DrawText(TEXT("Weather sets wind, current, and waves"), FLinearColor(0.7f, 0.78f, 0.86f), PanelX, PanelY, Font, 0.55f);
		PanelY += 18.f;
		DrawCommand(PanelX, PanelY, 160.f, 22.f, TEXT("Summer calm"), TEXT("Season0"));
		DrawCommand(PanelX + 166.f, PanelY, 160.f, 22.f, TEXT("Spring tide"), TEXT("Season1"));
		PanelY += 26.f;
		DrawCommand(PanelX, PanelY, 160.f, 22.f, TEXT("Autumn gale"), TEXT("Season2"));
		DrawCommand(PanelX + 166.f, PanelY, 160.f, 22.f, TEXT("Winter storm"), TEXT("Season3"));
		PanelY += 30.f;
		DrawText(FString::Printf(TEXT("Wind %.1f m/s  at %.0f deg"), Environment->GetWindSpeedMs(), Environment->GetWindDirectionDeg()), FLinearColor::White, PanelX, PanelY, Font, 0.62f);
		PanelY += 18.f;
		DrawCommand(PanelX, PanelY, 74.f, 22.f, TEXT("Wind -"), TEXT("WindDn"));
		DrawCommand(PanelX + 78.f, PanelY, 74.f, 22.f, TEXT("Wind +"), TEXT("WindUp"));
		DrawCommand(PanelX + 156.f, PanelY, 74.f, 22.f, TEXT("Dir -"), TEXT("WindL"));
		DrawCommand(PanelX + 234.f, PanelY, 74.f, 22.f, TEXT("Dir +"), TEXT("WindR"));
		PanelY += 28.f;
		DrawText(FString::Printf(TEXT("Current %.2f m/s  at %.0f deg"), Environment->GetCurrentSpeedMs(), Environment->GetCurrentDirectionDeg()), FLinearColor::White, PanelX, PanelY, Font, 0.62f);
		PanelY += 18.f;
		DrawCommand(PanelX, PanelY, 74.f, 22.f, TEXT("Cur -"), TEXT("CurDn"));
		DrawCommand(PanelX + 78.f, PanelY, 74.f, 22.f, TEXT("Cur +"), TEXT("CurUp"));
		DrawCommand(PanelX + 156.f, PanelY, 74.f, 22.f, TEXT("Dir -"), TEXT("CurL"));
		DrawCommand(PanelX + 234.f, PanelY, 74.f, 22.f, TEXT("Dir +"), TEXT("CurR"));
		PanelY += 28.f;
		DrawText(FString::Printf(TEXT("Waves %.1f m  at %.0f deg"), Environment->GetWaveHeightM(), Environment->GetWaveDirectionDeg()), FLinearColor::White, PanelX, PanelY, Font, 0.62f);
		PanelY += 18.f;
		DrawCommand(PanelX, PanelY, 74.f, 22.f, TEXT("Wave -"), TEXT("WaveDn"));
		DrawCommand(PanelX + 78.f, PanelY, 74.f, 22.f, TEXT("Wave +"), TEXT("WaveUp"));
		DrawCommand(PanelX + 156.f, PanelY, 74.f, 22.f, TEXT("Dir -"), TEXT("WaveL"));
		DrawCommand(PanelX + 234.f, PanelY, 74.f, 22.f, TEXT("Dir +"), TEXT("WaveR"));
		PanelY += 24.f;
		DrawText(TEXT("Period is fixed at 90 m wavelength"), FLinearColor(0.75f, 0.7f, 0.45f), PanelX, PanelY, Font, 0.52f);
		PanelY += 18.f;
		DrawCommand(PanelX, PanelY, 48.f, 22.f, TEXT("1x"), TEXT("Time1"));
		DrawCommand(PanelX + 52.f, PanelY, 48.f, 22.f, TEXT("5x"), TEXT("Time5"));
		DrawCommand(PanelX + 104.f, PanelY, 48.f, 22.f, TEXT("10x"), TEXT("Time10"));
		DrawCommand(PanelX + 156.f, PanelY, 48.f, 22.f, TEXT("20x"), TEXT("Time20"));
		DrawCommand(PanelX + 208.f, PanelY, 52.f, 22.f, Environment->IsPaused() ? TEXT("Run") : TEXT("Pause"), TEXT("Pause"));
		PanelY += 26.f;
		DrawCommand(PanelX, PanelY, 150.f, 22.f, TEXT("Reset ships"), TEXT("Reset"));
		PanelY += 26.f;
		DrawText(FString::Printf(TEXT("Sim time %.1f s    %.0fx"), Environment->GetSimTime(), Environment->GetTimeScale()), FLinearColor(0.85f, 0.92f, 1.f), PanelX, PanelY, Font, 0.62f);
		PanelY += 18.f;
		const FString Ack = Environment->WasCommandRejected()
			? TEXT("MMG rejected the last packet")
			: (Environment->HasPhysicsAck()
				? FString::Printf(TEXT("Applied  wind %.1f  cur %.2f  wave %.1f"), Environment->GetAppliedWindMs(), Environment->GetAppliedCurrentMs(), Environment->GetAppliedWaveHeightM())
				: TEXT("Waiting for MMG acknowledgement"));
		DrawText(Ack, Environment->HasPhysicsAck() ? FLinearColor(0.55f, 0.95f, 0.65f) : FLinearColor(1.f, 0.55f, 0.4f), PanelX, PanelY, Font, 0.55f);
	}

	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		const AFleetShip* Ship = *It;
		const FLinearColor Color = ShipColor(Ship->GetShipType());
		const FVector Location = Ship->GetActorLocation();
		const FVector Origin = Ship->GetRouteOrigin();
		const TArray<FVector>& Waypoints = Ship->GetWaypoints();

		FVector Previous(Origin.X, Origin.Y, 200.f);
		DrawWorldLine(FVector(Location.X, Location.Y, Location.Z + 400.f), Previous, Color);
		for (const FVector& Waypoint : Waypoints)
		{
			const FVector Point(Waypoint.X, Waypoint.Y, 400.f);
			DrawWorldLine(Previous, Point, Color);
			Previous = Point;
		}
		if (Waypoints.Num() > 0)
		{
			const FVector Destination(Waypoints.Last().X, Waypoints.Last().Y, 6800.f);
			const FVector DestinationScreen = Canvas->Project(Destination, false);
			if (DestinationScreen.Z > 0.f && DestinationScreen.Y > 150.f)
			{
				DrawText(TEXT("DEST"), Color, DestinationScreen.X + 14.f, DestinationScreen.Y - 16.f, Font, 0.8f);
			}
		}
	}

	Y += 30.f;
	for (TActorIterator<AFleetShip> It(GetWorld()); It; ++It)
	{
		const AFleetShip* Ship = *It;
		const FLinearColor Color = ShipColor(Ship->GetShipType());
		const FVector Location = Ship->GetActorLocation();
		const FString Status = FString::Printf(
			TEXT("%-16s  %5.1f kn   heading %05.1f   pos %6.0f m, %6.0f m"),
			*Ship->GetShipName(),
			Ship->GetSpeedKnots(),
			Heading360(Ship->GetHeadingDegrees()),
			Location.X / 100.f,
			Location.Y / 100.f);
		const FString Passage = FString::Printf(
			TEXT("    dest %5.0f m   fuel %4.2f t/h   leg %4.2f t   heave %+4.1f m   leeway %+4.1f deg   rudder %+5.1f deg"),
			Ship->GetDistanceRemainingMeters(),
			Ship->GetFuelTonnesPerHour(),
			Ship->GetFuelRemainingTonnes(),
			Ship->GetHeaveMeters(),
			Ship->GetLeewayDegrees(),
			Ship->GetRudderDegrees());
		DrawText(Status, Color, 16.f, Y, Font, Scale);
		Y += 22.f;
		DrawText(Passage, Color, 16.f, Y, Font, 0.82f);
		Y += 26.f;
	}
}
