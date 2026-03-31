Powder Technology 367 (2020) 376–389
Powder Technology
Development of processing strategies for multigraded selective laser melting of Ti6Al4V and IN718
Marco Giuseppe Scaramuccia $ ^{a} $ , Ali Gökhan Demir $ ^{a,*} $ , Leonardo Caprio $ ^{a} $ , Oriana Tassa $ ^{b} $ , Barbara Previtali $ ^{a} $
$ ^{a} $ Department of Mechanical Engineering, Politecnico di Milano, Via La Masa 1, 20156 Milan, Italy
$ ^{b} $ RINA Consulting - CSM S.p.A, Via Di Castel Romano 100, 00128 Roma, Italy

## ARTICLE INFO

Article history:
Received in revised form 8 January 2020

## Keywords

Additive manufacturing
Selective laser melting
Multi-material
Energy generation
Lightweight alloys
Superalloys

## Abstract

In energy generation applications, Ti- and Ni-alloys are widely used for their complementary features, where Ti-alloys provide lightweight structures while Ni-alloys are adaptable to high temperature use. The combination of these alloys into a single component through additive manufacturing is highly desirable. This work explores the multi-material selective laser melting (SLM) of a Ti6Al4V-IN718 material system to produce multigraded specimens. An in-house developed multi-material SLM platform with double hopper and a mixing chamber was employed. A work frame based on studying process feasibility through premixed blends and assessing the processability of multigraded components is presented. Material characteristics, in terms of chemistry, microhardness and microstructure are investigated and supported by thermodynamic calculations. Defect-free grading was achieved until 20 wt% inclusion of IN718 in Ti6Al4V. The results were interpreted to reveal the processability limits of the metallurgically incompatible alloys as well as the defect formation mechanisms.
© 2020 Elsevier B.V. All rights reserved.

## 1. Introduction

Selective laser melting (SLM) is a powder bed fusion additive manufacturing technique employing a laser beam as the energy source, which today has gained wide industrial acceptance $ [1,2] $ . Its flexibility allows the realization of complex geometrical shapes, reducing the lead time for the production of new parts, as no specific tooling is required. This technology proves to be a suitable candidate for the production of multi-material parts: tailoring different region of the components, depending on the specific operative conditions, would strongly enhance functionality of these parts, representing a significant added value. $ [3] $ Aerospace and energy are industrial fields where currently additive manufacturing, and SLM in particular, represent a viable alternative to traditional manufacturing processes. Turbine blades feature a very complex geometrical structure, with a wide number of internal channels, usually achieved by wire electric discharge machining (EDM) or electrochemical machining (ECM), which thus results in an expensive and multi-step manufacturing routes $ [4] $ . SLM, with its elevated geometrical flexibility, provides a good alternative allowing for the near net-shape production of the hollow blade. Focusing on gas turbines for aeronautical propulsion, the most widely used materials are titanium and nickel based alloys $ [5,6] $ . Titanium alloys offer a high strength-to-weight ratio, finding a wide range of applications in the compressor section of a gas turbine. On the other hand, the turbine section, given the higher temperatures, requires the adoption of nickel based superalloys. $ [7,8] $ The constant increase in performance required by the market has been constantly pushing the compression ratio to higher values, consequently increasing the temperature in the last stages of the compressor, making titanium alloys unsuitable, due to creep degradation and oxidation. As an alternative, nickel based superalloys have been used to realize the last compression stages, with a high penalty in terms of weight, being the density of those alloys nearly the double respect to titanium ones. These two alloy families are very dissimilar, showing different coefficients of thermal expansions and low metallurgical compatibility in general, making it difficult to bond them. Still, a patent by Honeywell already introduces the possibility to realize turbine blades via additive manufacturing with different superalloys to optimize the different portions of the component to the operative conditions $ [9] $ . Multi-material SLM process could then provide a viable alternative to bonding two different alloys, therefore producing a multi-material turbine blade, where the blade shaft and tip (exposed to the hot gases) could be realized with a creep resistant, nickel based superalloy, and the root, in a cooler region, with a titanium alloy for weight reduction.
Multi-material additive manufacturing has been studied with different material families changing the material between layers and/or within layers by means of different processing methods $ [10] $ . Concerning metals, the production of multi-material and graded components by means of directed energy deposition (DED) processes such
$ ^{*} $ Corresponding author.
https://doi.org/10.1016/j.powtec.2020.04.010
0032-5910/© 2020 Elsevier B.V. All rights reserved.

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
as laser metal deposition (LMD) has been demonstrated in literature. The material change and grading is intrinsically simpler for this process as multiple hoppers are industrially available for powder feeding $ [11,12] $ . SLM provides higher precision, smaller feature size and the means to produce lightweight structures based on lattices, which are appealing features for turbine blades that cannot be easily achieved by LMD $ [13] $ . Obtaining multigraded components with SLM is still a difficult task, given the need to handle more than one powder feedstock during the same build process. In literature, blended powders were used in SLM to produce in-situ alloys $ [14,15] $ as well as composite materials $ [16–22] $ . For in-situ alloying, the powder size and shape are found to be critical for the application. On the other hand, composite materials were produced by both blending powders with similar sizes as well as dressing the matrix materials with smaller nano-sized reinforcement particles. Recent works demonstrate the feasibility of multi-material SLM process, by using self-developed prototype equipment or modified industrial machines. Material variation was obtained layerwise, by depositing layers of new material on top of the previous one. Exner et al. used a double rake prototypal system, where they successfully produced Ag—Cu layered specimens $ [23] $ . Using a modified industrial machine, C_{18400} copper have been successfully deposited on top of 316 L stainless steel and AlSi10Mg. $ [24,25] $ Although the remelting action of the laser beam creates a smooth transition between the two materials for a certain number of layers, there is no control on the actual transition zone, the most critical in a multi-material part. A double hopper powder delivery system based on piezoelectric transducers permitted to realize Fe/Al-12Si specimen, with an intermixed region between the two materials $ [26] $ . Another approach towards a graded transition, by Mumtaz et al., features the deposition of layers of Waspaloy $ ^{\circledR} $ , gradually enriched with zirconia up to 10 vol%. $ [27] $ . To obtain material variation also within a single layer, selective recoaters have been developed. The systems employ a processing scheme where the first material is selectively deposited, then melted before the second one is delivered, and finally excess powder is vacuumed $ [28,29] $ . This aspect is often critical, as cross-contamination between different materials may occur. An alternative powder delivery method uses glass pipettes as “hopper-nozzles” to spread powder, by means of gas pressure or vibration feed, allowing a precise powder delivery, without the need to vacuuming the excess $ [30] $ . Koopmann et al. produced multi-material X38CrMoV5-ZrO $ _{2} $ /Al $ _{2} $ O $ _{3} $ components by separately processing the materials on an industrial SLM platform with high preheating capability (500 ^\circC) $ [31] $ . Mei et al. produced AISI 316 - IN718 - AISI 316 multi-material specimens with a direct transition between materials along the build direction in a similar fashion $ [32] $ . A different strategy, by Wei et al. introduces a micro vacuuming system, to selectively remove excess powder point-by-point after first material is molten $ [33] $ . The second one is deposited by means of selective ultrasonic powder dispensers. The system was demonstrated for use in anticounterfeiting $ [34] $ as well as producing composite support materials $ [35] $ . Anstaett et al. proposed an SLM system capable of depositing two different powders, where they successfully produced a multi-material component combining a Cu-alloy and a tool steel $ [36] $ . Recently Admatec developed an industrial SLM machine which spreads the raw material as a slurry, thus allowing to combine multiple materials $ [37] $ . By heating the feedstock the binder eventually evaporates and the metal powder can be successively processed.
Despite novel efforts in the field, multi-material SLM still requires further attention from the process development point of view. Current efforts have mainly concentrated on the development of material delivery strategies, whereas the SLM process parameters should be further studied in order to resolve process defects arising from the grading conditions. While several attempts have been made in literature to change material composition locally or between layers, the processing of graded compositions requires further attention. A graded transition between two different powders is challenging both from machine architecture perspective as well as the process parameter selection due to possible metallurgical incompatibilities.
Accordingly, this work presents the multi-material SLM of Ti6Al4V and IN718 alloys on an in-house developed multi-material SLM platform. Both Ti6Al4V [38–40] and IN718 [41–43] are characterized by good processability via SLM. The present material combination is highly appealing for energy applications, while their graded processing poses challenges due to the low compatibility of the alloying elements. The experimental work proposes a process development scheme where first single and pre-mixed blends were processed for selecting the adequate parameters. Finally, samples with complete grading were produced with the novel SLM system. The produced samples were characterized for their material properties and the formation mechanisms are further explained by thermodynamic calculations.

## 2. Systems and materials

## 2.1. Materials

The powder feedstock was chosen concerning the processability of the single alloys, pre-mixed blends, as well as the graded multi-material specimens. Since the work aims to produce multi-material transition between the two powder feedstocks and the fraction of the two materials should be varied, they were chosen at similar size distributions. The choice of different powder size distributions can be advantageous in different cases such as better distributing a single element with smaller particle size in a prealloyed powder. However, for the present work the aim has been to freely vary the chemical composition between the two alloys. Hence, both feedstocks were also chosen to be spherical in shape as conventionally used in single alloy processing by SLM. Ti6Al4V and Inconel 718 gas atomized powders (LPW, Runcorn, United Kingdom) were used throughout the work. Ti6Al4V powder size powder size distribution was D10:23 $ \mu $ m, D50:33 $ \mu $ m, D90:46 $ \mu $ m. IN718 powder size distribution was D10:18 $ \mu $ m, D50:30 $ \mu $ m, D90:47 $ \mu $ m. Both powder feedstocks were spherical in shape (respectively visible in Fig. 4a and b). Base plates (substrates) used for the process were 12 mm thick Ti6Al4V plates for deposition of Ti6Al4V, pre-mixed Ti6Al4V/IN718 and the graded transition specimen, while 3 mm thick IN718 plates were used for IN718 deposition.

## 2.2. Multi-material selective laser melting platform

A flexible prototype system for SLM namely Powderful was used throughout this work [44]. The mechanical system consisted of a custom-made powder bed able to process small quantities of powder (<500 g), which was placed in a sealed chamber. Prior to processing an inertization procedure was carried out, where a cycle of vacuum down to -950 mbar and Ar purging up to 10 mbar was applied three times. The light source was a single mode fiber laser with 1 kW maximum power (nLIGHT alta, Vancouver, WA, USA). The laser beam was collimated with a 75 mm lens, which was manipulated and focused by a scanner head (Smart Move GmbH, Garching bei München, German). The collimated beam was focused with a 420 mm f-theta lens. In this configuration, the beam diameter at the focal plane ( $ d_{0} $ ) was determined as 78 $ \mu $ m. The control of the mechanical system and the monitoring of the machine state were carried out using LabVIEW software (National Instruments, Austin, TX). The scan path trajectory was designed using Scan Master Designer software (Cambridge Technologies, Bedford, MA). The main system characteristics are shown in Table 1. The prototype system was designed to assess processability issues of new materials [45,46], phenomenological studies concerning the process physics [47], and the study of new processing strategies [48] employing small sized samples typically with 5x5x5 mm $ ^{3} $ dimensions. Such dimensions are relatively small compared to the parts produced by industrial SLM systems. Still, they are significant to characterize the processing conditions in terms of porosity and the cracking behaviour as well as the chemical composition required at the proof-of-concept level.

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Table 1
Main characteristics of the open SLM platform powderful.

| Parameter | Value |
| --- | --- |
| Laser emission wavelength, $ \lambda $ | 1080 nm |
| Max. laser power, $ P_{max} $ | 1000 W |
| Beam quality factor, $ M^{2} $ | 1.19 |
| Nominal beam diameter on focal plane, $ d_{0} $ | 78 $ \mu $ m |
| Build platform area (DxWxH) | 60x60x20 mm $ ^{3} $ |

The multi-material capability was provided by a double-hopper system (see Fig. 1). The step by step functioning principle of the mixing unit is shown in Fig. 2. Two types of powders are placed in separate hoppers (Powder A and Powder B). In step 1 and step 2, the desired quantities of the materials are by means of piezoelectric transducers. In step 3, the mixing chamber present underneath the two hoppers which blends the powders by means of rotating blades. The design of the blades allows them to mix or discharge the powder, depending on the rotation direction. The powder mixing chamber ensured a correct blending by before releasing the mixture to the powder bed. At the end of step 3, the mixed powder is discharged into a lower hopper. Finally in step 4, the mixed powder is released on the powder bed using another piezoelectric transducer. The following operations are similar to a conventional SLM system, where a wiper spreads the powder on the powder bed. Eventual excess powder in the mixing chamber can be discharged (for recollection) away from the build area. The system allows for using separate powders or powder mixtures on demand between different layers. Hence, material change, use of intermediate layers and gradient transitions can be achieved along the build direction.
The powder mixture composition was controlled by a prior calibration procedure. The dosage of each powder was controlled by the piezoelectric transducers of the multi-material unit. Powder feed rate was obtained as a function of transducers vibration amplitude controlled by the applied voltage and vibration time. Blending experiments were carried out to assess the mixing error as a function of the target IN718 content. Ti6Al4V and IN718 were dosed to achieve a total of 5 g blend powder. A precision scale was used for the characterization. The powders were dosed in a sequence where first the Ti6Al4V powder was dosed and its weight was measured, followed by the dosing of the IN718 power and the weighing of the mix. The concentrations of the two materials was calculated from the measured weights. The experiments were carried out for 4 blends as well as the single materials. Three replications were produced. Fig. 3 shows the concentration of the two powders dosed by the mixing system as a function of the target IN718 content. The mixtures produced shown an error smaller than 5.
Fig. 2. Functioning principle of the mixing unit shown in different steps.
Fig. 1. a) Powderful SLM prototype, placed inside the processing chamber, positioned under the scanner head. b) Detail of the multi-material unit, mounted on the prototype, filled with Ti6Al4V and IN718 powders. c) CAD model of the multi material unit.

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 3. Composition of the powder dosed by the mixing unit as a function of the target IN718 content. The dashed lines represent the desired trend without dosing errors for both the materials.
Fig. 4. SEM acquisitions of powders morphology by means of a backscattered electron detector. Darker particles (dark gray in c,d,e, and f) are Ti6Al4V, brighter ones (white in c,d,e, and f) are IN718. The first two images show the base materials, while the latter show the different Ti6Al4V/IN718 mixtures used to calibrate the multi-material unit. a) Ti6Al4V b) IN718 c) 10 wt% IN718 mixture d) 20 wt% IN718 mixture e) 40 wt% IN718 mixture f) 60 wt% IN718 mixture.

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
wt% with respect to the target composition. Fig. 4 shows the SEM images of the single and blended powders. It can be noted that the mixing system allowed for a homogenous dispersion of the powders.

## 2.3. Experimental plan

The experimental plan was completed in three different stages concerning the single materials, pre-mixed blends, and the build of the multigraded specimens. Energy density (E) parameter was used as a reference for the definition of the experimental plans, and is defined in Eq. 1:
$$ E=\frac{P}{h\cdot\nu\cdot z} $$
(1)
where P is the laser power, v the scan speed, h the hatch distance and z is layer thickness. The first experimental campaign focused on the processability of the two single material, aiming to obtain pore and crack free specimens. Layer thickness was fixed at 50 µm and the focal position of the laser beam (f) was fixed on the powder bed. Laser power, scan speed and hatch distance were varied in order to find the energy density range which granted fully dense specimen. Cubic samples with 5x5x5 mm³ dimensions were produced. In Table 2 the experimental plans are reported for both Ti6Al4V and IN718. Energy density input range was 21–320 J/mm³ for Ti6Al4V and 63–900 J/mm³ for IN718.
The second part of the experimental plan aimed to define the processability region of Ti6Al4V and IN718 powder mixtures. A campaign was conducted to define the process parameters set which granted pore and crack free parts. Four different premixed blends were used, with 10, 20, 30, and 40 wt% target IN718. In Table 3 the target chemical compositions of the materials and the blends are reported. Powders were mixed in the desired ratios with the innovative powder mixer unit of the open SLM platform. All blends were processed with the same set of process parameters, with an energy density input range of 141–400 J/mm $ ^{3} $ as reported in Table 4. This range is defined on the basis of the results of the campaign on single alloys: lower and upper limits correspond to the values which granted full densification for, respectively, Ti6Al4V and IN718. In Table 4 the details of the experimental plan are reported. Two replicates for each condition were produced.
The final experiments were devoted to the realization of specimens with a graded composition along the build direction. Two replicates were produced. The first material deposited was Ti6Al4V, for 42 layers. IN718 quantity was then increased in the following layers, in discrete steps of 5%wt, reaching 20% (for a total of four different blends). For each blend 12 layers of feedstock powder were deposited. Energy density determined according to the results of the premixed blend experiments, and was varied during the build according to the blend in use, as shown in Table 5.
All the specimens produced in the three experimentations were mounted in resin and polished for metallographic analysis. Optical microscopy images were taken of the entire specimen cross-section in order to determine porosity and crack formation (Quick Vision ELF QV-202, Mitutoyo, Kawasaki, Japan). Apparent density was measured
Fixed and varied parameter for production testing of Ti6Al4V and IN718 powders.

<table><tr><td colspan="4">Fixed parameters</td></tr><tr><td>Layer thickness</td><td>z ( $ \mu $ m)</td><td>50</td><td></td></tr><tr><td>Focal position</td><td>f (mm)</td><td>0</td><td></td></tr><tr><td>Process gas</td><td></td><td>Ar</td><td></td></tr><tr><td colspan="2">Varied parameters</td><td>Ti6Al4V</td><td>IN718</td></tr><tr><td>Hatch distance</td><td>h ( $ \mu $ m)</td><td>50-100</td><td>50-100</td></tr><tr><td>Laser power</td><td>P (W)</td><td>200-300-400</td><td>250-350-450</td></tr><tr><td>Scan speed</td><td>v (mm/s)</td><td>500-1900</td><td>100-1000</td></tr><tr><td>Energy density</td><td>E (J/mm $ ^{3} $ )</td><td>21-320</td><td>63-900</td></tr></table>

Nominal chemical composition of Ti6Al4V, IN718 and the target compositions of the four produced blends. All values are reported in wt%.

| IN718 wt% | Ti | Al | V | Ni | Cr | Fe | Nb | Mo |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0 (Ti6Al4V) | 88.93 | 6.40 | 4.10 | 0.00 | 0.00 | 0.18 | 0.00 | 0.00 |
| 10 | 83.10 | 4.2 | 3.25 | 5.00 | 1.96 | 1.75 | 0.47 | 0.26 |
| 20 | 74.36 | 3.85 | 2.91 | 10.00 | 3.92 | 3.50 | 0.95 | 0.53 |
| 30 | 64.74 | 3.45 | 2.53 | 15.53 | 6.07 | 5.42 | 1.47 | 0.82 |
| 40 | 56.87 | 3.13 | 2.22 | 20.00 | 9.80 | 7.00 | 1.89 | 1.05 |
| 100 (IN718) | 0.97 | 0.48 | 0.00 | 52.99 | 19.04 | 18.20 | 4.90 | 2.73 |

Table 4
Fixed and varied parameter for processing premixed Ti6Al4V/IN718 powder blends.

<table><tr><td colspan="3">Fixed parameters</td></tr><tr><td>Layer thickness</td><td>z ( $ \mu $ m)</td><td>50</td></tr><tr><td>Hatch distance</td><td>h ( $ \mu $ m)</td><td>50</td></tr><tr><td>Focal position</td><td>f (mm)</td><td>0</td></tr><tr><td>Process gas</td><td></td><td>Ar</td></tr><tr><td colspan="3">Varied parameters</td></tr><tr><td>IN718 content</td><td>(wt%)</td><td>10-20-30-40</td></tr><tr><td>Laser power</td><td>P (W)</td><td>300-450</td></tr><tr><td>Scan speed</td><td>v (mm/s)</td><td>350-850</td></tr></table>

Process parameters for the graded transition specimen as a function of the target IN718 content.

| No of layers | IN718 [%wt] | P [W] | v [mm/s] | h [ $ \mu $ m] | z [ $ \mu $ m] | E [J/mm $ ^{3} $ ] |
| --- | --- | --- | --- | --- | --- | --- |
| 42 | 0 | 300 | 700 | 50 | 50 | 170 |
| 12 | 5 | 300 | 700 | 50 | 50 | 170 |
| 12 | 10 | 300 | 700 | 50 | 50 | 170 |
| 12 | 15 | 300 | 550 | 50 | 50 | 218 |
| 12 | 20 | 300 | 450 | 50 | 50 | 267 |

employing image processing software. Images were then binarized to calculate the apparent density which was determined as follows:
$$ \rho_{A}=\frac{A_{tot}-A_{pore}}{A_{tot}} $$
(2)
where $ A_{tot} $ is the total area considered and $ A_{pore} $ is the total area of the pores [49]. Selected samples have been also observed by SEM (EVO-50, Carl Zeiss, Oberkochen, Germany) and elemental composition evaluated by EDX. Microhardness measurements have been carried out on all of the specimens. Vickers microhardness was measured on samples with 500 gf load and 15 s dwell time. Material microstructure was analysed by optical microscopy (UM200I, EchoLAB, Paderno Dugnano, Italy). As an aid to describe the observed phenomenon, thermodynamic calculations have been performed using Thermo-Calc software (Stockholm, Sweden).

## 3. Results

## 3.1. Processability of single alloys and pre-mixed powders

## 3.1.1. Density

In Fig. 5 cross sections from specimen produced with different levels of energy density input are reported. In Fig. 6 plot reports the measured density for all specimen respect to energy density input. For Ti6Al4V and IN718 specimens, an increase in E granted an increase in density, up to a certain threshold, after which full densification is obtained. Full densification threshold observed for Ti6Al4V is 120 J/mm $ ^{3} $ , while for IN718 is 250 J/mm $ ^{3} $ . These values were assumed, indicatively, as lower and upper boundaries for the definition of the experimental campaign.

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 5. Cross sections of the deposited specimens.
for the premixed blends. Despite the high density measured, further increase of energy density resulted in swelling of the specimens. Above $ 500 \, J/mm^{3} $ the process was not feasible for geometrical inaccuracy.
The same analysis was carried on for 10 and 20 wt% IN718 specimen. In particular, for all the conditions no porosity was detected. For 30 and 40 wt% IN718 specimen the density was not measured since the presence of cracks hindered the image-based density calculation, however, porosity was not observed in the sections. The formed cracks are expected to be due to the formation of hard and fragile intermetallic phases. The size of the cracks with the 30 and 40 wt% IN718 are

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 6. Apparent density of the produced specimens as a function of energy density.
comparable to the size of the specimens. These cracks were visible on the produced specimens reaching the side walls of the specimens after the SLM process. The formation of these cracks were associated to the release of the thermal stresses by the breakage of the fragile intermetallic phases. The high cooling rates of the SLM process is known to induce high thermal stresses, which can generate severe cracking in the presence of fragile phases [50,51]. Preheating of the baseplate or the powder bed can be a solution to provide a solution to reduce the thermal stresses, as well as the formation of fragile phases, which should be assessed according to the material composition [52,53].

## 3.1.2. Crack formation

Fig. 7 reports the crack presence as a function of the process parameters and the chemical composition of the pre-mixed powders. It can be seen that both the replications were not cracked in all tested conditions.
Fig. 7. Crack presence as a function of process parameters and IN718 content in the blend. The severity of the processing condition was assessed in terms of the number of cracked replicates (none, one, or both).
with 10 wt% IN718 blended with Ti6Al4V. Crack presence started with the blend containing 20 wt% IN718 below 266 J/mm $ ^{3} $ energy density. All specimens with 30 wt% and 40 wt% IN718 exhibited severe macro cracks, regardless of the process parameters. For these conditions, a qualitative analysis on the internal sections showed that specimens produced with high energy density input exhibited less and smaller cracks.
Crack initiation and propagation usually occurs at point of stress concentration and weak bonding at the interface. Material immiscibility inhibits bonding, and mismatch in thermal properties such as large differences in the coefficient of thermal expansion induce thermal stresses. The formation of brittle intermetallic phases could also increase the susceptibility to failure even at relatively low thermal stresses. It has been reported by Chatterjee et al. [54] and Shah et al. [55] that the presence of $ Ti_{2}Ni $ and $ TiNi_{3} $ were responsible for cracking in dissimilar laser welding of Ti with Ni, and in direct laser deposition of Ti6Al4V and IN718, respectively.
In order to clarify the mechanisms that governs the crack formation in the different blends investigated thermodynamic calculations were performed. Although the SLM process is in a non-equilibrium condition, performing these calculations over a range of temperatures allows for the analysis at temperatures that the system may experience.
Thermodynamic calculations were performed on the blend systems (from 0% to 40% IN718), using elemental composition data reported in Table 3. The results of calculation are reported in Fig. 8.a where the pseudo phase diagram of Ti6Al4V alloyed with IN718 is shown.
The solidification range ( $ \Delta T_{solidification} $ ), can be associated to the weldability of a metal alloy and thus can be extended to evaluate the processability by means of SLM. The compositions that exhibit large solidification temperature ranges are generally susceptible to solidification cracking. $ \Delta T_{solidification} $ of pure Ti6Al4V is 16 ^\circC. The increase of IN718 fraction in the blend results in a progressive reduction of both $ T_{liquidus} $ and $ T_{solidus} $ , with an abrupt drop of the latter. As a consequence, the solidification range is significantly increased. For 10 wt% IN718 the solidification range is increased up to 191 ^\circC. For 20 wt% IN718, $ \Delta T_{solidification} $ achieves the highest value of 288 ^\circC, decreasing slightly with the further increase of IN718 to 194 ^\circC for 30 wt% and 119 ^\circC for 40 wt%.

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 8. a) Pseudo-phase diagram of Ti6Al4V blended with IN718. b) Fractions of liquid and Ti $ _{2} $ Ni phases as function of temperature for different Ti6Al4V /IN718 blends.
These results suggest that the main cause of the crack formation was not solidification cracking, since the 20 wt% IN718 blend has a low defect density even though it is characterized by the highest $ \Delta T_{solidification} $ . There are two important points that can be drawn from the phase diagram in Fig. 8a. The thermodynamic calculations predict the progressive destabilization of $ \alpha $ -phase, with temperature formation decreased to values lower than 600 ^\circC for the 40% blend. Critical transformation temperature is strongly decreased by the addition of Ni and Cr, and the beta phase transformation results inhibited due the fast cooling rates. The high solidification rates are responsible for the strong segregation of Ni, Mo and Cr in the last solidifying zones, particularly at the melt pool boundaries. This result can be associated to the decrease of martensitic phase that almost disappears for IN718 fractions higher than 20 wt%. As shown in Fig. 8b, the thermodynamic calculations also point out the formation of the hard intermetallic phase $ Ti_{2}Ni $ . Results of the thermodynamic calculations highlight an increase of $ Ti_{2}Ni $ formation at equilibrium temperature with increased IN718 fraction. For 30 wt% and 40 wt% IN718 blends, $ Ti_{2}Ni $ starts to form in the liquid phase. The formation of this intermetallic phase can strongly affect material behaviour. As well known for Ni superalloys, the formation of a high fraction of $ Ni_{3}Al $ intermetallic phase is associated to a drop of weldability. The formation of cracks with a high fraction of IN718 can also be linked to the formation of these intermetallics.

## 3.1.3. Microhardness

Microhardness (HV) of the specimens produced with the energy density level that granted full densifications and no cracks was measured. Fig. 9 reports the microhardness measurements for the single materials and the blends along with the energy density chosen for the representative defect-free conditions. Measured hardness for Ti6Al4V is $ 402 \pm 7 $ HV, for IN718 $ 255 \pm 13 $ HV. The inclusion of 10 wt% IN718 in the blend provided a decrease in hardness to $ 381 \pm 21 $ HV compared to Ti6Al4V. The alloying elements introduced with IN718, acting as beta-stabilizers for titanium, could promote the formation of beta phase, softer than the alpha one. For the blends with 20, 30 and 40 wt% IN718 microhardness was much higher, due to the probable formation of hard intermetallic phases. Measured hardnesses were $ 477 \pm 16 $ HV for 20 wt%, $ 684 \pm 48 $ HV for 30 wt% and $ 582 \pm 27 $ HV for 40 wt% IN718 content.

## 3.1.4. Microstructure

Fig. 10 depicts the microstructure of the Ti6Al4V sample. Optical microscopy analysis revealed that the microstructure of the components

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 9. Vickers Microhardness as a function of IN718 wt% content in the blend. Energy densities allowing defect-free processing were chosen for comparison.
Fig. 10. Optical microscopy images of the Ti6Al4V sample (E = 178 J/mm³). a) \beta-grains seen at lower magnification, b) \alpha' laths seen at higher magnification.
was composed of fine acicular $ \alpha' $ grains. The $ \alpha' $ martensitic laths are organised within prior $ \beta $ grain boundaries with different inclinations, mainly at $ \sim \pm45^{\circ} $ with respect to the build direction. The columnar grains are the result of epitaxial growth of the previous layer upon successive laser scans. Some lack of fusion defects could also be identified.
Fig. 11 shows representative OM and SEM micrographs of IN718 specimens. The typical layer by layer SLM manufacturing characteristics, as well as the melt pool morphology are clearly visible. Columnar grains across several layers can also be distinguished, with a very fine dendritic structure. The SEM micrograph shows a detail of the dendritic structure of the material, with evidence of strong segregation in the interdendritic zones, which resulted enriched in Nb and Mo. The bright phases, observable in the BSE image, achieve Nb content up to 23.7 wt% (measured by EDX analysis) and Mo up to 2.5%. According to literature, these high element contents can be associated to the formation of $ Ni_{3}Nb\delta $ -phase in the segregated areas [56,57].
Fig. 12 shows the SEM micrographs of pre-mixed blends along with the chemical composition analysis. The SEM micrographs in Fig. 12a belonging to 10 wt% IN718 blend shows a non-uniform microstructure across the specimen surface. The deposited layers are clearly distinguishable and no alpha martensitic lathes could be observed. The alloying elements which compose IN718 (mainly Ni, Cr and Fe), act as beta-stabilizers for titanium, promoting the growth and retaining of this phase down to room temperature. The dendritic microstructure is not clearly observable within the layers, indicating a low microsegregation level. Instead, the presence of macrosegregated areas located at the layer interfaces is clearly evidenced. In these areas, Ni reaches values up to 15 wt% and Cr up to 3.6 wt%. In Fig. 12b the micrographs of the 20 wt% IN718 blend are shown. SEM analysis reveals a complex (yet uniform, as stated) microstructure, with clear evidence of a second phase nucleated in the interdendritic zones. The formation of \beta phase is expected with the increase of IN718 content. SEM/EDX analysis puts in to evidence that the second phase is rich in Ni (up to 17% wt). The further IN718 fraction increase, in the 30 wt% IN718 and 40 wt% IN718 blends, promotes the nucleation of the intermetallic Ti₂Ni phase (bright phase in Fig. 12c and d). It can be expected that the \alpha-Ti + Ti₂Ni

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 11. Optical microscopy (a,b) and SEM (c) images of the IN718 sample (E = 300 J/mm³).

<table><tr><td>10 wt% IN718</td><td>Al</td><td>V</td><td>Cr</td><td>Fe</td><td>Ni</td><td>Nb</td><td>Mo</td><td>Ti</td></tr><tr><td>Red box</td><td>5.18</td><td>3.83</td><td>1.54</td><td>1.78</td><td>5.08</td><td>0.66</td><td>0.3</td><td>Bal</td></tr><tr><td>A</td><td>3.74</td><td>2.76</td><td>3.65</td><td>4.07</td><td>14.60</td><td>3.830</td><td>0.5</td><td>Bal</td></tr><tr><td>B</td><td>5.39</td><td>4.00</td><td>1.37</td><td>1.95</td><td>4.01</td><td>0.19</td><td>0.34</td><td>Bal</td></tr><tr><td colspan="9"></td></tr><tr><td>20 wt% IN718</td><td>Al</td><td>V</td><td>Cr</td><td>Fe</td><td>Ni</td><td>Nb</td><td>Mo</td><td>Ti</td></tr><tr><td>Red box</td><td>4.37</td><td>3.47</td><td>3.44</td><td>3.55</td><td>10.21</td><td>1.70</td><td>0.86</td><td>Bal</td></tr><tr><td>A</td><td>3.77</td><td>2.3</td><td>2.80</td><td>4.36</td><td>18.17</td><td>0.98</td><td>0.26</td><td>Bal</td></tr><tr><td>B</td><td>4.68</td><td>3.65</td><td>3.96</td><td>3.62</td><td>8.35</td><td>1.51</td><td>1.04</td><td>Bal</td></tr><tr><td colspan="9"></td></tr><tr><td>30 wt% IN718</td><td>Al</td><td>V</td><td>Cr</td><td>Fe</td><td>Ni</td><td>Nb</td><td>Mo</td><td>Ti</td></tr><tr><td>Red box</td><td>3.81</td><td>2.14</td><td>6.44</td><td>6.96</td><td>19.05</td><td>4.11</td><td>0.63</td><td>Bal</td></tr><tr><td>A</td><td>4.44</td><td>3.64</td><td>8.96</td><td>5.87</td><td>13.19</td><td>2.51</td><td>20.9</td><td>Bal</td></tr><tr><td>B</td><td>3.74</td><td>2.66</td><td>7.09</td><td>8.55</td><td>21.18</td><td>2.53</td><td>0.55</td><td>Bal</td></tr><tr><td colspan="9"></td></tr><tr><td>40 wt% IN718</td><td>Al</td><td>V</td><td>Cr</td><td>Fe</td><td>Ni</td><td>Nb</td><td>Mo</td><td>Ti</td></tr><tr><td>Red box</td><td>3.66</td><td>54.64</td><td>2.33</td><td>7.08</td><td>20.69</td><td>2.80</td><td>1.41</td><td>Bal</td></tr><tr><td>A</td><td>2.41</td><td>1.48</td><td>4.10</td><td>4.59</td><td>11.82</td><td>2.51</td><td>0.95</td><td>Bal</td></tr><tr><td>B</td><td>3.96</td><td>4.53</td><td>11.81</td><td>6.56</td><td>10.32</td><td>4.27</td><td>3.87</td><td>Bal</td></tr></table>
Fig. 12. SEM micrographs of premixed blends. a) 10 wt% IN718, E = 165 J/mm $ ^{3} $ , b) 20 wt% IN718, E = 267 J/mm $ ^{3} $ , c) 30 wt% IN718, E = 400 J/mm $ ^{3} $ , d) 40 wt% IN718, E = 400 J/mm $ ^{3} $ .

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 13. Cross-section of the graded specimen with the schematic representation of the grading structure.
eutectoid transformation starts at grain boundaries of the $ \beta $ phase. Due to the massive precipitation of the intermetallic phase the dendritic solidification microstructure is no more observable.

## 3.2. Multi-material SLM with a graded transition

Graded transition specimen were cross sectioned without removing them from the substrate. Process parameters used for producing these specimens were determined from the previous experiments. The internal section appeared fully dense and crack free. No delamination between layers could be observed, nor between the first layers and the Ti6Al4V substrate. As seen in Fig. 13, the graded specimen was successfully built up to the 20 wt% IN718 content.
The hardness profile of the deposited component as a function of the build height is reported in Fig. 14. The increase of hardness values is smoother with respect to the samples with the same nominal fraction of IN718 (Fig. 9). The difference can be attributed to the dilution effect occurring due to the diffusion of alloying elements among adjacent previously solidified layers.
Fig. 15 shows the microstructure of the multigraded specimens taken at different build height positions. The local chemical composition measurements taken are provided in Table 6. The variation of the chemical composition measurements along the build direction is shown in Fig. 16 (data has been acquired in points along the build direction which corresponds to the different Ti6Al4V/IN718 target compositions). The decrease in Ti content along the build direction, together with the increased presence of IN718 alloying elements, is coherent with the graded deposition. The dilution of the Ti6Al4V composition, due to the layer interdiffusion, is also observable by the corresponding Cr, Fe and Nb increase and the reduction of Al and V. The remelting effect induced by the laser beam (the previous solidified layers are melted together with the last deposited layer of powder) contributes in creating a smoother transition from one blend to the other, thus creating a whole new, functionally graded material. This trend was consistent with that observed for hardness. The highest hardness values are obtained in the layers strongly enriched in Ni, Nb, Cr and Fe content, presumably associated to the formation of hard intermetallic phases.
Another influential factor concerning the material microstructure is the position of the investigated region due to the cooling direction [58]. As the deposited height grows the solidification rates can change also due to heat accumulation. Such phenomenon is more marked in DED processes compared to SLM due to the slower cooling rates [59]. However, the influence of the position is expected to be much less significant
Fig. 14. Microhardness of the multigraded specimens as a function of the build height.

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 15. Microstructure along the build direction of the multigraded specimens at different heights: a) 0.7 mm, b) 2.0 mm, c) 2.8 mm, d) 3 mm, e) 3.62 mm, f) 4.10 mm.
compared to the chemical composition change induced by the material mixing.

## 4. Conclusions

In this work, an innovative multi-material SLM prototype system was employed to study the production of premixed and multigraded
Table 6
Local chemical compositions revealed in Fig. 15. All values are reported in wt%.

| Height | Region | Al | Ti | V | Cr | Fe | Ni | Nb |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2.00 mm | A | 6.11 | 84.63 | 3.49 | 0.28 | 0.60 | 0.98 | 3.81 |
| 2.00 mm | B | 5.52 | 86.54 | 3.39 | 0.19 | 0.32 | 1.00 | 3.03 |
| 2.80 mm | A | 4.89 | 75.79 | 3.50 | 3.15 | 3.21 | 6.32 | 3.23 |
| 2.80 mm | B | 5.92 | 86.36 | 4.16 | 0.06 | - | 0.16 | 3.33 |
| 3.62 mm | A | 4.59 | 77.83 | 3.48 | 2.49 | 2.49 | 6.76 | 2.80 |
| 3.62 mm | B | 5.64 | 86.11 | 4.10 | 0.21 | 0.33 | 0.94 | 2.66 |
| 3.62 mm | C | 4.51 | 65.99 | 2.35 | 3.56 | 4.70 | 15.36 | 3.53 |
| 4.10 mm | A | 4.70 | 79.04 | 3.39 | 2.12 | 2.54 | 6.91 | 3.09 |
| 4.10 mm | B | 4.91 | 82.01 | 3.68 | 1.11 | 1.74 | 4.08 | 2.46 |
| 4.10 mm | C | 3.90 | 67.77 | 2.96 | 2.24 | 4.09 | 15.68 | 3.36 |

Ti6Al4V/IN718 specimens. The main conclusions of the research are as follows:
• As a base line for the multigraded deposition, the optimal processing parameters to obtain full density specimens for each alloy singularly were identified (respectively $ E \geq 160 J/mm^{3} $ for Ti6Al4V and $ E \geq 300 J/mm^{3} $ for IN718). Pore-free specimens were then characterized in terms of microhardness and microstructure.
• Processability of the Ti6Al4V and IN718 premixed powder blends was determined in the second part of the experimental investigation: results show that for 10 wt% IN718 blend full density is achieved with the same energy density input required to process 100% Ti6Al4V. 20 wt% IN718 blended alloy could be successfully produced without cracks with E > 266 J/mm³. Specimens produced with IN718 content greater than 20 wt% showed cracking regardless of the processing conditions. The metallographic analysis along with thermodynamic calculations indicated that the generation of fragile Ti₂Ni phases occurs at the liquid state. This fact was attributed as the main cause for the severe cracking.
• Multigraded Ti6Al4V/IN718 components were deposited via SLM. The gradual increase in IN718 content and the use of suitable process parameters allowed to realize a functionally graded material: microhardness showed a gradual increment that could be explained by

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Fig. 16. Chemical composition profile along the build direction of the multigraded specimen.
the increased presence of hard inclusions. Thermodynamic calculations revealed themselves as a helpful tool to design crack free components with graded compositions by controlling the solidification range and avoiding the crack formation due to the excessive presence of brittle phases.

## Declaration of Competing Interest

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

## Acknowledgements

The authors wish to express their gratitude to Optoprim Srl and nLIGHT Inc. for their collaboration and technical support. This work was supported by European Union, Repubblica Italiana, Regione Lombardia and FESR for the project MADE4LO under the call “POR FESR 2014-2020 ASSE I - AZIONE I.1.B.1.3”. The Italian Ministry of Education, University and Research is acknowledged for the support provided through the Project "Department of Excellence LIS4.0 - Lightweight and Smart Structures for Industry 4.0".

## References

[1] J.M. Lee, S.L. Sing, M. Zhou, W.Y. Yeong, 3D bioprinting processes: a perspective on classification and terminology, Int. J. Bioprint. 4 (2018) 1–10, https://doi.org/10.18063/IJB.v4i2.151.
[2]. ISO, INTERNATIONAL STANDARD ISO/ASTM 52900, Additive manufacturing – general principles – terminology, Int. Organ. Stand. 2015 (2015) https://doi.org/10.1520/ISOASTM52900-15.
[3] B.G. Mellor, Multiple material additive manufacturing – part 1: a review, Virtual Phys. Prototyp. 8 (2013) 19–50, https://doi.org/10.1080/17452759.2013.778175.
[4] F. Klocke, A. Klink, D. Veselovac, D. Keith, S. Leung, M. Schmidt, J. Schilp, G. Levy, J. Kruth, CIRP Annals - Manufacturing Technology Turbomachinery component manufacture by application of electrochemical, electro-physical and photonic processes, CIRP Ann. Manuf. Technol. 63 (2014) 703–726, https://doi.org/10.1016/j.cirp.2014.05.004.
[5] B.M. Peters, J. Kumpfert, C.H. Ward, C. Leyens, Titanium alloys for aerospace applications, Adv. Eng. Mater. 5 (2003) 419–427, https://doi.org/10.1002/adem.200310095.
[6] N.R. Muktinutalapati, Materials for Gas Turbines – An Overview, 2006.
[7] M. Whittaker, Titanium in the Gas Turbine Engine, 4, 2011.
[8] I.A.E.O. Ikechukwu, P.O. Ebunilo, E. Ikpe, Material selection for high pressure (HP) compressor blade of an aircraft engine, Int. J. Adv. Mater. Res. 2 (2016) 59–65.
[9] D.G. Godfrey, M.C. Morris, Multi-Material Turbine Components, 2013.
[10] M. Vaezi, S. Chianrabutra, B. Mellor, S. Yang, Multiple material additive manufacturing – part 1: a review, Virtual Phys. Prototyp. 8 (2013) 19–50, https://doi.org/10.1080/17452759.2013.778175.
[11] F. Brueckner, M. Riede, M. Müller, F. Marquardt, R. Willner, A. Seidel, E. Lopéz, C. Leyens, E. Beyer, Enhanced manufacturing possibilities using multi-materials: in laser metal deposition, LIA Today 26 (2018) 10–12, https://doi.org/10.2351/1.5040639.

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
[12] K. Shah, I. Ul Haq, A. Khan, S.A. Shah, M. Khan, A.J. Pinkerton, Parametric study of development of Inconel-steel functionally graded materials by laser direct metal deposition, Mater. Des. 54 (2014) 531–538, https://doi.org/10.1016/j.matdes.2013.08.079.
[13] S. Liu, Y.C. Shin, Additive manufacturing of Ti6Al4V alloy: a review, Mater. Des. 164 (2019) 107552, https://doi.org/10.1016/j.matdes.2018.107552.
[14] P. Vora, K. Mumtaz, I. Todd, N. Hopkinson, AlSi12 in-situ alloy formation and residual stress reduction using anchorless selective laser melting, Addit. Manuf. 7 (2015) 12–19, https://doi.org/10.1016/j.addma.2015.06.003.
[15] C.A. Biffi, A.G. Demir, M. Coduri, B. Previtali, A. Tuissi, Laves phases in selective laser melted TiCr1.78 alloys for hydrogen storage, Mater. Lett. 226 (2018) https://doi.org/10.1016/j.matlet.2018.05.028.
[16] N. Baluc, J.L. Boutard, S.L. Dudarev, M. Rieth, J.B. Correia, B. Fournier, J. Henry, F. Legendre, T. Leguey, M. Lewandowska, R. Lindau, E. Marquis, A. Muñoz, B. Radiguet, Z. Oksiuta, Review on the EFDA work programme on nano-structured ODS RAF steels, J. Nucl. Mater. 417 (2011) 149–153, https://doi.org/10.1016/j.jnucmat.2010.12.065.
[17] S. Dadbakhsh, L. Hao, Effect of Al alloys on selective laser melting behaviour and microstructure of in situ formed particle reinforced composites, J. Alloys Compd. 541 (2012) 328–334, https://doi.org/10.1016/j.jallcom.2012.06.097.
[18] D. Gu, G. Meng, C. Li, W. Meiners, R. Poprawe, Selective laser melting of TiC/Ti bulk nanocomposites: influence of nanoscale reinforcement, Scr. Mater. 67 (2012) 185–188, https://doi.org/10.1016/j.scriptamat.2012.04.013.
[19] S.J. Zinkle, G.S. Was, Materials challenges in nuclear energy, Acta Mater. 61 (2013) 735–758, https://doi.org/10.1016/j.actamat.2012.11.004.
[20] D.E. Cooper, N. Blundell, S. Maggs, G.J. Gibbons, Additive layer manufacture of Inconel 625 metal matrix composites, reinforcement material evaluation, J. Mater. Process. Technol. 213 (2013) 2191–2200, https://doi.org/10.1016/j.jmatprotec.2013.06.021.
[21] B. AlMangour, D. Grzesiak, J.M. Yang, In situ formation of TiC-particle-reinforced stainless steel matrix nanocomposites during ball milling: feedstock powder preparation for selective laser melting at various energy densities, Powder Technol. 326 (2018) 467–478, https://doi.org/10.1016/j.powtec.2017.11.064.
[22] W.H. Yu, S.L. Sing, C.K. Chua, C.N. Kuo, X.L. Tian, Particle-reinforced metal matrix nanocomposites fabricated by selective laser melting: a state of the art review, Prog. Mater. Sci. 104 (2019) 330–379, https://doi.org/10.1016/j.pmatsci.2019.04.006.
[23] H. Exner, P. Regenfuss, L. Hartwig, S. Klötzer, R. Ebert, Selective Laser Micro Sintering With a Novel Process, vol. 5063, 2003 145–151.
[24] S.L. Sing, L.P. Lam, D.Q. Zhang, Z.H. Liu, C.K. Chua, Materials characterization interfacial characterization of SLM parts in multi-material processing : intermetallic phase formation between AlSi10Mg and C_{18400} copper alloy, Mater. Charact. 107 (2015) 220–227, https://doi.org/10.1016/j.matchar.2015.07.007.
[25] Z.H. Liu, D.Q. Zhang, S.L. Sing, C.K. Chua, L.E. Loh, Interfacial characterization of SLM parts in multi-material processing: metallurgical diffusion between 316L stainless steel and C_{18400} copper alloy, Mater. Charact. 94 (2014) 116–125.
[26] A.G. Demir, B. Previtali, Multi-material selective laser melting of Fe/Al-12Si components, Manuf. Lett. J. 11 (2017) 8–11, https://doi.org/10.1016/j.mfglet.2017.01.002.
[27] K.A. Mumtaz, N. Hopkinson, Laser melting functionally graded composition of Waspaloy and zirconia powders, J. Mater. Sci. 42 (2007) 7647–7656, https://doi.org/10.1007/s10853-007-1661-3.
[28] M. Ott, M.F. Zaeh, Multi-Material Processing in Additive Manufacturing, 2010 195–203.
[29] Y. Chivel, New approach to multi-material processing in selective laser melting, in: 9th Int, Conf. Photonic Technol. LANE 2016 (2016) 891–898, https://doi.org/10.1016/j.phpro.2016.08.093.
[30] P. Kumar, J.K. Santosa, E. Beck, S. Das, P. Kumar, J.K. Santosa, E. Beck, S. Das, Direct-write deposition of fine powders through miniature hopper-nozzles for multimaterial solid freeform fabrication, Rapid Prototyp. J. 10 (2015) 14–23, https://doi.org/10.1108/13552540410512499.
[31] J. Koopmann, J. Voigt, T. Niendorf, Additive manufacturing of a steel–ceramic multi-material by selective laser melting, Metall. Mater. Trans. B Process Metall. Mater. Process. Sci. 50 (2019) 1042–1051, https://doi.org/10.1007/s11663-019-01523-1.
[32] X. Mei, X. Wang, Y. Peng, H. Gu, G. Zhong, S. Yang, Interfacial characterization and mechanical properties of 316L stainless steel/inconel 718 manufactured by selective laser melting, Mater. Sci. Eng. A 758 (2019) 185–191, https://doi.org/10.1016/j.msea.2019.05.011.
[33] C. Wei, L. Li, X. Zhang, Y. Chueh, CIRP annals - manufacturing technology 3D printing of multiple metallic materials via modi fi ed selective laser melting, CIRP Ann. Manuf. Technol. 67 (2018) 245–248, https://doi.org/10.1016/j.cirp.2018.04.096.
[34] C. Wei, Z. Sun, Y. Huang, L. Li, Embedding anti-counterfeiting features in metallic components via multiple material additive manufacturing, Addit. Manuf. 24 (2018) 1–12, https://doi.org/10.1016/j.addma.2018.09.003.
[35] C. Wei, Y.-H. Chueh, X. Zhang, Y. Huang, Q. Chen, L. Li, Easy-to-remove composite support material and procedure in additive manufacturing of metallic components using multiple material laser-based powder bed fusion, J. Manuf. Sci. Eng. 141 (2019) 1, https://doi.org/10.1115/1.4043536.
[36] C. Anstaett, C. Seidel, G. Reinhart, Fabrication of 3D multi-material parts using laser-based powder bed fusion, Proc. 28th Annu. Int. Solid Free. Fabr. Symp. Addit. Manuf. Conf. 2017, pp. 1–9.
[37] Admatec, Laserflex Conflux, (n.d.) https://admateceurope.com/products/#laserflex2020, Accessed date: 4 June 2019.
[38] S. Amin Yavari, R. Wauthle, J. Van Der Stok, A.C. Riemslag, M. Janssen, M. Mulier, J.P. Kruth, J. Schrooten, H. Weinans, A.A. Zadpoor, Fatigue behavior of porous biomaterials manufactured using selective laser melting, Mater. Sci. Eng. C 33 (2013) 4849–4858, https://doi.org/10.1016/j.msec.2013.08.006.
[39] S. Zhang, Q. Wei, L. Cheng, S. Li, Y. Shi, Effects of scan line spacing on pore characteristics and mechanical properties of porous Ti6Al4V implants fabricated by selective laser melting, Mater. Des. 63 (2014) 185–193, https://doi.org/10.1016/j.matdes.2014.05.021.
[40] I. Yadroitsev, P. Krakhmalev, I. Yadroitsava, Selective laser melting of Ti6Al4V alloy for biomedical applications: temperature monitoring and microstructural evolution, J. Alloys Compd. 583 (2014) 404–409, https://doi.org/10.1016/j.jallcom.2013.08.183.
[41] Z. Wang, K. Guan, M. Gao, X. Li, X. Chen, X. Zeng, The microstructure and mechanical properties of deposited-IN718 by selective laser melting, J. Alloys Compd. 513 (2012) 518–523, https://doi.org/10.1016/j.jallcom.2011.10.107.
[42] Q. Jia, D. Gu, Selective laser melting additive manufacturing of Inconel 718 superalloy parts: densification, microstructure and properties, J. Alloys Compd. 585 (2014) 713–721, https://doi.org/10.1016/j.jallcom.2013.09.171.
[43] K.N. Amato, S.M. Gaytan, L.E. Murr, E. Martinez, P.W. Shindo, J. Hernandez, S. Collins, F. Medina, Microstructures and mechanical behavior of Inconel 718 fabricated by selective laser melting, Acta Mater. 60 (2012) 2229–2239, https://doi.org/10.1016/j.actamat.2011.12.032.
[44] A.G. Demir, L. Monguzzi, B. Previtali, Selective laser melting of pure Zn with high density for biodegradable implant manufacturing, Addit. Manuf. 15 (2017) https://doi.org/10.1016/j.addma.2017.03.004.
[45] A.G. Demir, L. Monguzzi, B. Previtali, Selective laser melting of pure Zn with high density for biodegradable implant manufacturing, Addit. Manuf. 15 (2017) 20–28, https://doi.org/10.1016/j.addma.2017.03.004.
[46] M. Colopi, A.G. Demir, L. Caprio, B. Previtali, Limits and solutions in processing pure cu via selective laser melting using a high-power single-mode fiber laser, Int. J. Adv. Manuf. Technol. (2019) https://doi.org/10.1007/s00170-019-04015-3.
[47] L. Caprio, A.G. Demir, B. Previtali, Influence of pulsed and continuous wave emission on melting efficiency in selective laser melting, J. Mater. Process. Technol. 266 (2018) 429–441, https://doi.org/10.1016/j.jmatprotec.2018.11.019.
[48] A.G. Demir, L. Mazzoleni, L. Caprio, M. Pacher, B. Previtali, Complementary use of pulsed and continuous wave emission modes to stabilize melt pool geometry in laser powder bed fusion, Opt. Laser Technol. 113 (2019) 15–26, https://doi.org/10.1016/j.optlastec.2018.12.005.
[49] A.B. Spierings, M. Schneider, R. Eggenberger, Comparison of density measurement techniques for additive manufactured metallic parts, Rapid Prototyp. J. 17 (2011) 380–386, https://doi.org/10.1108/13552541111156504.
[50] K. Kempen, B. Vrancken, S. Buls, L. Thijs, J. Van Humbeeck, J.-P. Kruth, Selective laser melting of crack-free high density M2 high speed steel parts by baseplate preheating, J. Manuf. Sci. Eng. 136 (2014), 061026. https://doi.org/10.1115/1.4028513.
[51] D. Buchbinder, W. Meiners, N. Pirch, K. Wissenbach, J. Schrage, Investigation on reducing distortion by preheating during manufacture of aluminum components using selective laser melting, J. Laser Appl. 26 (2014), 012004. https://doi.org/10.2351/1.4828755.
[52] J. Van Humbeeck, S. Buls, L. Thijs, K. Kempen, B. Vrancken, J.-P. Kruth, Selective laser melting of crack-free high density M2 high speed steel parts by baseplate preheating, J. Manuf. Sci. Eng. 136 (2014), 061026. https://doi.org/10.1115/1.4028513.
[53] J. Gussone, Y.C. Hagedorn, H. Gherekhloo, G. Kasperovich, T. Merzouk, J. Hausmann, Microstructure of $ \gamma $ -titanium aluminide processed by selected laser melting at elevated temperatures, Intermetallics. 66 (2015) 133–140, https://doi.org/10.1016/j.intermet.2015.07.005.
[54] S. Chatterjee, T.A. Abinandanan, K. Chattopadhyay, Microstructure development during dissimilar welding: case of laser welding of Ti with Ni involving intermetallic phase formation, J. Mater. Sci. 41 (2006) 643–652, https://doi.org/10.1007/s10853-006-6480-4.
[55] K. Shah, I.U. Haq, S.A. Shah, F.U. Khan, M.T. Khan, S. Khan, Experimental study of direct laser deposition of Ti-6Al-4V and Inconel 718 by using pulsed parameters, Sci. World J. 2014 (2014) 1–6, https://doi.org/10.1155/2014/841549.
[56] L.L. Parimi, G. Ravi, D. Clark, M.M. Attallah, Microstructural and texture development in direct laser fabricated IN718, Mater. Charact. 89 (2014) 102–111, https://doi.org/10.1016/j.matchar.2013.12.012.
[57] A. Mostafa, I.P. Rubio, V. Brailovski, M. Jahazi, M. Medraj, Structure, texture and phases in 3D printed IN718 alloy subjected to homogenization and HIP treatments, Metals (Basel) 7 (2017) 1–23, https://doi.org/10.3390/met7060196.
[58] B. Song, X. Zhao, S. Li, C. Han, Q. Wei, S. Wen, J. Liu, Y. Shi, Differences in microstructure and properties between selective laser melting and traditional manufacturing for fabrication of metal parts: a review, Front. Mech. Eng. 10 (2015) 111–125, https://doi.org/10.1007/s11465-015-0341-2.
[59] J.H.K. Tan, S.L. Sing, W.Y. Yeong, Microstructure modelling for metallic additive manufacturing: a review, Virtual Phys. Prototyp. 2759 (2019) https://doi.org/10.1080/17452759.2019.1677345.

=== SUPPLEMENTARY OCR LINES (paragraph blocks missing from main text) ===

## Page 1

## Page 2

## Page 3

378
M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
Table 1
Main characteristics of the open SLM platform powderful.

## Page 4

## Page 5

## Page 6

## Page 7

## Page 8

## Page 9

## Page 10

M.G. Scaramuccia et al. / Powder Technology 367 (2020) 376–389
385
Fig. 11. Optical microscopy (a,b) and SEM (c) images of the IN718 sample (E = 300 J/mm³).

## Page 11

## Page 12

## Page 13

## Page 14