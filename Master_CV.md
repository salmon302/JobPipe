%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Candidate: Seth Nenninger
% ATS-Optimized Version
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

\documentclass[letterpaper,11pt]{article}

% ----- PACKAGES -----
\usepackage[empty]{fullpage}
\usepackage[english]{babel}
\usepackage{geometry}
\usepackage{hyperref}
\usepackage{enumitem}
\usepackage{titlesec}
\usepackage{lmodern}
\usepackage[T1]{fontenc} % Ensures better font encoding for character extraction

% Ensure that the generated PDF is machine-readable/ATS-parsable
\input{glyphtounicode}
\pdfgentounicode=1

% ----- DOCUMENT GEOMETRY (ULTRA-TIGHT MARGINS) -----
\geometry{
    left=0.6in,
    right=0.6in,
    top=0.3in, 
    bottom=0.3in
}

% ----- HYPERLINK SETUP -----
\hypersetup{
    colorlinks=true,
    urlcolor=black, % ATS parsers prefer black text
    linkcolor=black,
    pdfborder={0 0 0}
}
\urlstyle{same}

% ----- SECTION FORMATTING -----
\titleformat{\section}{
    \vspace{4pt}\scshape\raggedright\large\bfseries 
}{}{0em}{}[\color{black}\titlerule \vspace{-2pt}]
\titlespacing{\section}{0pt}{4pt}{4pt}

% ----- CUSTOM COMMANDS -----
% Simple text-based layout (no tables or complex grids) for ATS parsing
\newcommand{\resumeEntry}[4]{
    \vspace{2pt}
    \noindent\textbf{#1}\hfill{#2}
    \newline
    \noindent\textit{#3}\hfill\textit{#4}
    \vspace{-3pt}
}

% Standard round bullet points mapped to standard characters
\newcommand{\resumeItemListStart}{\begin{itemize}[label=$\bullet$, leftmargin=1.1em, itemsep=0pt, parsep=0pt, topsep=2pt]}
\newcommand{\resumeItemListEnd}{\end{itemize}}

% ----- DOCUMENT START -----
\begin{document}

%---------- HEADING ----------
\begin{center}
    \textbf{\Huge Seth Nenninger}
    \vspace{5pt}
    
    Fort Myers, FL \quad | \quad \href{mailto:sethnenninger@gmail.com}{sethnenninger@gmail.com} \quad | \quad \href{https://www.linkedin.com/in/seth-nenninger-bb3897178/}{LinkedIn} \quad |  \quad \href{https://github.com/salmon302}{GitHub}
\end{center}

%---------- PROFESSIONAL SUMMARY ----------
\section{Professional Summary}
\vspace{1pt}
\noindent Software Engineer with a proven track record of developing high-performance applications, real-time simulation engines, and automated data pipelines. Adept at leveraging C++ and Python to build scalable solutions, with hands-on experience ensuring 100\% data integrity and strict quality assurance in highly regulated environments. Passionate about applying rigorous engineering principles to solve complex problems across enterprise systems, healthcare technology, and software infrastructure.

%---------- SKILLS ----------
\section{Skills}
\vspace{3pt}
\noindent\textbf{Core Languages:} C++, Python, C\#, JavaScript, Structured Query Language (SQL), AVR Assembly
\vspace{5pt}

\noindent\textbf{Frameworks \& Libraries:} React, FastAPI, Qt, Pandas, PyTorch, OpenGL, JUCE
\vspace{5pt}

\noindent\textbf{Infrastructure \& Tools:} Amazon Web Services (AWS) Elastic Compute Cloud (EC2), Docker, Ansible, Git, Linux, Jira
\vspace{5pt}

\noindent\textbf{Domain Expertise:} Real-Time Engines, Quality Assurance (QA) Protocols, Regulatory Compliance (FDA/cGMP), Data Integrity
\vspace{5pt}

%---------- EDUCATION ----------
\section{Education}
    \resumeEntry
        {Master of Science (MS) in Simulation \& Modeling}
        {August 2026 – May 2028 (Expected)}
        {University of Central Florida}
        {Orlando, FL}
        
    \resumeEntry
        {Bachelor of Science (BS) in Software Engineering}
        {August 2021 – May 2026}
        {Florida Gulf Coast University}
        {Fort Myers, FL}
        
    \resumeEntry
        {Coursework towards Bachelor of Science (BS) in Biochemistry}
        {August 2020 – May 2021}
        {Rochester Institute of Technology}
        {Rochester, NY}

%---------- WORK EXPERIENCE ----------
\section{Work Experience}
    \resumeEntry
        {Backend Engineer Intern}
        {August 2025 - Present}
        {Exonicus}
        {Fort Myers, FL}
    \resumeItemListStart
        \item Architected a Local Area Network (LAN)-based remote control system and dynamic shader parameter foundation for a real-time layered visualization tool, successfully showcased at International Meeting for Simulation in Healthcare (IMSH) 2026 in partnership with Kitware.
        \item Engineered the backend integration between a high-fidelity data engine and Unity, optimizing processing logic and state synchronization to guarantee a consistent 60 Frames Per Second (FPS) performance.
        \item Developed robust validation protocols and comprehensive technical documentation, successfully streamlining the handoff of core infrastructure modules to cross-functional teams and reducing onboarding time.
    \resumeItemListEnd

    \resumeEntry
        {Biologics Processor \& Quality Assurance (QA) Associate}
        {March 2025 – Present}
        {Grifols}
        {Fort Myers, FL}
    \resumeItemListStart
        \item Operate within a highly regulated environment, strictly adhering to Standard Operating Procedures (SOPs) and Current Good Manufacturing Practices (cGMP).
        \item Process over 1,750 biological samples weekly with 99.8\% accuracy, maintaining zero compliance-related rejections during stringent quality assurance audits.
        \item Maintain data integrity for over 3,000 sensitive records, ensuring full traceability, secure data handling, and compliance with federal regulatory standards.
    \resumeItemListEnd

    \resumeEntry
        {Research Assistant – Natural Language Processing (NLP) \& Data Analysis}
        {October 2025 - December 2025}
        {Florida Gulf Coast University}
        {Fort Myers, FL}
    \resumeItemListStart
        \item Utilized Python (Pandas, SciPy, Scikit-learn) to process and analyze large datasets, successfully identifying linguistic markers for predictive modeling.
        \item Built automated data pipelines to perform cross-dataset comparisons, achieving a high statistical correlation of 0.81 in context similarity analysis.
    \resumeItemListEnd
    
    \resumeEntry
        {Student Life Safety Assistant}
        {January 2022 – May 2023}
        {Florida Gulf Coast University}
        {Fort Myers, FL}
    \resumeItemListStart
        \item Conducted rigorous inspections of critical infrastructure, ensuring university-wide compliance with safety codes and operational standards for over 5,000 campus residents.
    \resumeItemListEnd

%---------- PROJECTS ----------
\section{Projects}
    \resumeEntry
        {SMARTArm: Voice \& Vision Controlled Robotic Teleoperation Framework}
        {March 2026 – April 2026}
        {Python, OpenCV, MediaPipe, Flask, C/C++, ESP32, TensorFlow Lite Micro (TFLM)}
        {GitHub: \href{https://github.com/salmon302/SMARTArm/tree/Jacks-Branch}{salmon302/SMARTArm}}
    \resumeItemListStart
        \item Architected a multi-modal teleoperation framework for a 6 Degrees of Freedom (DOF) robotic arm utilizing a "Software-First" approach, achieving real-time spatial control via a single standard webcam without depth sensors.
        \item Engineered real-time kinematic mapping using Google MediaPipe 3D world landmarks, applying dot and cross-product vector mathematics to calculate precise finger flexion and palm orientation.
        \item Resolved joint occlusion and Machine Learning (ML) tracking jitter by integrating the MANO parametric hand model for biomechanical constraints and implementing an adaptive, first-order One Euro low-pass filter.
        \item Designed a high-performance embedded communication bridge using an ESP32-S3 Microcontroller Unit (MCU), replacing JSON with MessagePack binary serialization to compress data payloads by up to 70\% and achieve sub-10ms command latency.
        \item Deployed an Edge Artificial Intelligence (AI) fail-safe by shrinking a neural network by 75\% via 8-bit integer quantization, running a TensorFlow Lite Micro (TFLM) model natively on the MCU for offline emergency processing.
    \resumeItemListEnd

    \resumeEntry
        {Ad-Velocity: High-Throughput Click Ingestor}
        {February 2026 – April 2026}
        {C\#, .NET Web Application Programming Interface (API), Redis, AWS DynamoDB}
        {GitHub: \href{https://github.com/salmon302/Ad-Velocity}{salmon302/Ad-Velocity}}
    \resumeItemListStart
        \item Architected a scalable, high-throughput ingestion pipeline using a Write-Behind caching pattern for reliable data processing of real-time click events.
        \item Engineered the system to maintain sub-millisecond API latency while successfully buffering traffic spikes of up to 10x normal volume.
        \item Built a Python Graphical User Interface (GUI) load testing tool to simulate high-volume traffic and validate system performance under stress.
    \resumeItemListEnd
    
    \resumeEntry
        {DSATrain: AI-Powered Technical Interview Platform}
        {July 2025 – September 2025}
        {FastAPI, React}
        {GitHub: \href{https://github.com/salmon302/DSATrain}{salmon302/DSATrain}}
    \resumeItemListStart
        \item Developed a full-stack application using FastAPI and React to provide intelligent, real-time feedback on user-submitted Data Structures and Algorithms (DSA) coding challenges.
    \resumeItemListEnd

    \resumeEntry
        {Cloud Infrastructure Security Automation}
        {August 2024 – December 2024}
        {Ansible, Amazon Web Services (AWS), Linux}
        {Portfolio: \href{https://salmon302.github.io/Resume/}{salmon302.github.io/Resume}}
    \resumeItemListStart
        \item Deployed secure AWS EC2 infrastructure using Ansible playbooks for automated provisioning and security hardening.
        \item Mitigated simulated cybersecurity attacks, including Structured Query Language (SQL) injection and Distributed Denial of Service (DDoS), through robust system configuration and monitoring.
    \resumeItemListEnd

    \resumeEntry
        {Textbook Divider: Optical Character Recognition (OCR) Automation Tool}
        {May 2024 – Present}
        {Python, Machine Learning (ML)}
        {GitHub: \href{https://github.com/salmon302/Textbook-Divider}{salmon302/Textbook-Divider}}
    \resumeItemListStart
        \item Built an automated document processing tool using Tesseract Optical Character Recognition (OCR), achieving a 99.2\% text extraction accuracy rate.
        \item Optimized image processing algorithms to reduce processing time to 6.7 seconds per page, yielding a 4x efficiency gain in document ingestion.
    \resumeItemListEnd

    \resumeEntry
        {PYXEngine: Real-Time Audio/DSP Platform}
        {July 2025 – September 2025}
        {Python, SuperCollider}
        {Personal Project}
    \resumeItemListStart
        \item Architected a high-performance Python-based Digital Signal Processing (DSP) engine integrating SuperCollider for real-time signal synthesis.
        \item Implemented test automation and maintained extensive documentation, strictly mirroring software development lifecycles used in commercial engineering.
    \resumeItemListEnd

    \resumeEntry
        {PumpSim: Medical Infusion Pump Simulation}
        {January 2024 – May 2024}
        {AVR Assembly, Embedded Systems}
        {Portfolio: \href{https://salmon302.github.io/Resume/}{salmon302/Portfolio}}
    \resumeItemListStart
        \item Developed a functional simulation of a medical infusion pump using AVR Assembly on an Arduino Microcontroller Unit (MCU).
        \item Programmed precise timing interrupts and user interface logic to simulate critical drug delivery mechanisms safely and accurately.
    \resumeItemListEnd

%---------- AWARDS ----------
\section{Awards}
    \resumeEntry
        {Best Virtual Reality (VR) Game (Medical Training)}
        {December 2025}
        {I/ITSEC Serious Games Showcase \& Challenge}
        {Orlando, FL}
    \resumeItemListStart
        \item Awarded for "MilExTS," a Virtual Reality (VR) Tactical Combat Casualty Care Trainer, recognizing excellence in simulation-based medical education.
    \resumeItemListEnd
    
    \resumeEntry
        {Hertz Company Challenge Winner}
        {February 2025}
        {EagleHacks Hackathon}
        {Fort Myers, FL}
    \resumeItemListStart
        \item Won 1st Place for the best utilization of proprietary datasets to create a scalable software solution.
    \resumeItemListEnd

\end{document}