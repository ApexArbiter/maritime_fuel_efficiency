#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "WaterInteractionTest.generated.h"

class UBuoyancyComponent;
class UStaticMeshComponent;

UCLASS()
class MARITIMEFUELEFFICIENCY_API AWaterProbe : public AActor
{
	GENERATED_BODY()

public:
	AWaterProbe();

	void SetupProbe(float InMassKg);
	virtual void BeginPlay() override;

	UBuoyancyComponent* GetBuoyancy() const { return Buoyancy; }
	UStaticMeshComponent* GetBody() const { return Body; }
	float GetMassKg() const { return MassKg; }

private:
	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UStaticMeshComponent> Body;

	UPROPERTY(VisibleAnywhere)
	TObjectPtr<UBuoyancyComponent> Buoyancy;

	UPROPERTY()
	float MassKg = 200.f;
};

UCLASS()
class MARITIMEFUELEFFICIENCY_API AWaterInteractionTest : public AActor
{
	GENERATED_BODY()

public:
	AWaterInteractionTest();

	virtual void BeginPlay() override;

private:
	void SampleWaves();
	void FinishTest();

	bool bWavesPassed = false;
	float WaveSpanCm = 0.f;

	UPROPERTY()
	TObjectPtr<AWaterProbe> Wood;

	UPROPERTY()
	TObjectPtr<AWaterProbe> Iron;

	FTimerHandle WaveTimer;
	FTimerHandle FinishTimer;
};
