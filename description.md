                                                                                                                                  
• # ThreatLens: what the project does                                                                                             
                                                                                                                                  
  ThreatLens is a real-time, explainable intrusion-detection dashboard.                                                           
                                                                                                                                  
  It accepts structured security logs, detects suspicious behavior, assigns risk scores, stores alerts, explains them using a     
  local LLM, and displays everything in a React dashboard.                                                                        
                                                                                                                                  
  The core flow is:                                                                                                               
                                                                                                                                  
  Log event                                                                                                                       
    ↓                                                                                                                             
  Validate and store event                                                                                                        
    ↓                                                                                                                             
  Update/check user behavioral profile                                                                                            
    ↓                                                                                                                             
  Run detection rules                                                                                                             
    ↓                                                                                                                             
  Adjust alert score using user context                                                                                           
    ↓                                                                                                                             
  Store alert and update user risk                                                                                                
    ↓                                                                                                                             
  Push alert over WebSocket                                                                                                       
    ↓                                                                                                                             
  Generate AI explanation                                                                                                         
    ↓                                                                                                                             
  Display to analyst                                                                                                              
                                                                                                                                  
  The main project overview is in README.md, while the design reasoning is in files/ARCHITECTURE.md.                              
                                                                                                                                  
  ## 1. Technology stack                                                                                                          
                                                                                                                                  
  Backend:                                                                                                                        
                                                                                                                                  
  - Python                                                                                                                        
  - FastAPI                                                                                                                       
  - SQLAlchemy                                                                                                                    
  - PostgreSQL                                                                                                                    
  - Alembic migrations                                                                                                            
  - Pydantic validation                                                                                                           
  - pytest                                                                                                                        
                                                                                                                                  
  Frontend:                                                                                                                       
                                                                                                                                  
  - React 18                                                                                                                      
  - Vite                                                                                                                          
  - Tailwind CSS                                                                                                                  
  - Recharts                                                                                                                      
  - React Router                                                                                                                  
  - WebSocket client                                                                                                              
                                                                                                                                  
  AI:                                                                                                                             
                                                                                                                                  
  - Ollama running locally                                                                                                        
  - Mistral model by default                                                                                                      
                                                                                                                                  
  The backend normally runs on port 8002; the frontend runs on 5173.                                                              
                                                                                                                                  
  ## 2. Backend structure                                                                                                         
                                                                                                                                  
  The backend lives in backend/app.                                                                                               
                                                                                                                                  
  ### main.py                                                                                                                     
                                                                                                                                  
  backend/app/main.py creates the FastAPI application.                                                                            
                                                                                                                                  
  It is responsible for:                                                                                                          
                                                                                                                                  
  - Registering API routers                                                                                                       
  - Configuring CORS                                                                                                              
  - Exposing /health                                                                                                              
  - Starting and stopping the risk-decay scheduler                                                                                
  - Initializing the WebSocket event-loop integration                                                                             
                                                                                                                                  
  The API routes are mounted below /api/v1.                                                                                       
                                                                                                                                  
  ### database.py                                                                                                                 
                                                                                                                                  
  backend/app/database.py creates:                                                                                                
                                                                                                                                  
  - SQLAlchemy engine                                                                                                             
  - Session factory                                                                                                               
  - Declarative model base                                                                                                        
  - FastAPI database dependency                                                                                                   
                                                                                                                                  
  Production expects PostgreSQL. Tests use an in-memory SQLite database.                                                          
                                                                                                                                  
  ### config.py                                                                                                                   
                                                                                                                                  
  backend/app/config.py centralizes configuration.                                                                                
                                                                                                                                  
  Important defaults include:                                                                                                     
                                                                                                                                  
  Brute-force window:       60 seconds                                                                                            
  Brute-force thresholds:   5 / 10 / 20 failures                                                                                  
  Port-scan window:         3 seconds                                                                                             
  Port-scan thresholds:     15 / 50 distinct ports                                                                                
  Unusual-IP bootstrap:     3 login events                                                                                        
  Low severity:             0–25                                                                                                  
  Medium severity:          26–50                                                                                                 
  High severity:            51–75                                                                                                 
  Critical severity:        76–100                                                                                                
                                                                                                                                  
  It also controls:                                                                                                               
                                                                                                                                  
  - Database URL                                                                                                                  
  - CORS origins                                                                                                                  
  - LLM host/model                                                                                                                
  - Risk-score weights                                                                                                            
  - Decay rates                                                                                                                   
  - Connection-pool sizes                                                                                                         
                                                                                                                                  
  ## 3. Log ingestion                                                                                                             
                                                                                                                                  
  The main ingestion endpoint is:                                                                                                 
                                                                                                                                  
  POST /api/v1/log                                                                                                                
                                                                                                                                  
  Implemented in backend/app/api/logs.py.                                                                                         
                                                                                                                                  
  A valid event looks like:                                                                                                       
                                                                                                                                  
  {                                                                                                                               
    "user_id": "alice",                                                                                                           
    "ip": "192.168.1.10",                                                                                                         
    "timestamp": "2026-08-10T10:30:00Z",                                                                                          
    "event_type": "LOGIN_FAILURE",                                                                                                
    "status": "failed",                                                                                                           
    "port": null,                                                                                                                 
    "endpoint": null,                                                                                                             
    "user_agent": "Chrome",                                                                                                       
    "country": "IN"                                                                                                               
  }                                                                                                                               
                                                                                                                                  
  Supported event types are defined in backend/app/schemas/common.py:                                                             
                                                                                                                                  
  - LOGIN_SUCCESS                                                                                                                 
  - LOGIN_FAILURE                                                                                                                 
  - API_CALL                                                                                                                      
  - PORT_ACCESS                                                                                                                   
  - LOGOUT                                                                                                                        
                                                                                                                                  
  Pydantic rejects unknown input fields, so malformed or unexpected payloads fail early.                                          
                                                                                                                                  
  ## 4. What happens inside ingestion                                                                                             
                                                                                                                                  
  The ingestion path is deliberately ordered.                                                                                     
                                                                                                                                  
  ### Step 1: Upsert the user                                                                                                     
                                                                                                                                  
  The system creates the user if they do not exist, or updates their last_seen_at.                                                
                                                                                                                                  
  ### Step 2: Store the raw log                                                                                                   
                                                                                                                                  
  The event is persisted in the log_events table.                                                                                 
                                                                                                                                  
  The original structured payload is also stored as JSON for auditability.                                                        
                                                                                                                                  
  ### Step 3: Load the behavioral profile                                                                                         
                                                                                                                                  
  Each user gets one persistent BehaviorProfile.                                                                                  
                                                                                                                                  
  This profile contains:                                                                                                          
                                                                                                                                  
  - Known IP addresses                                                                                                            
  - Login count                                                                                                                   
  - Typical login hour                                                                                                            
  - Login-hour variance                                                                                                           
  - Typical time between logins                                                                                                   
  - Last login/logout timestamps                                                                                                  
  - Average session duration                                                                                                      
  - Deviation score                                                                                                               
  - Rolling user risk score                                                                                                       
                                                                                                                                  
  ### Step 4: Calculate current deviation                                                                                         
                                                                                                                                  
  The system compares the current event with the user’s previous baseline.                                                        
                                                                                                                                  
  Deviation considers:                                                                                                            
                                                                                                                                  
  - New IP address                                                                                                                
  - Unusual login hour                                                                                                            
  - Unusual login frequency                                                                                                       
                                                                                                                                  
  The result is between 0.0 and 1.0.                                                                                              
                                                                                                                                  
  Important: the event is compared against the old profile before the current event is added to it. Otherwise, a new IP would     
  immediately become “known” and would never be detected.                                                                         
                                                                                                                                  
  ### Step 5: Run detection rules                                                                                                 
                                                                                                                                  
  The detector registry runs all detectors.                                                                                       
                                                                                                                                  
  Implemented in backend/app/detection/registry.py.                                                                               
                                                                                                                                  
  The current registry contains:                                                                                                  
                                                                                                                                  
  - Brute-force detector                                                                                                          
  - Port-scan detector                                                                                                            
  - Unusual-IP detector                                                                                                           
                                                                                                                                  
  ### Step 6: Update the behavioral profile                                                                                       
                                                                                                                                  
  Only after detection is complete, the event updates the profile:                                                                
                                                                                                                                  
  - Login count increases                                                                                                         
  - IP is added to known IPs                                                                                                      
  - Login-time EMA is updated                                                                                                     
  - Session information is updated                                                                                                
  - Last event time changes                                                                                                       
                                                                                                                                  
  ### Step 7: Commit everything                                                                                                   
                                                                                                                                  
  The event, profile, and alerts are committed in one transaction.                                                                
                                                                                                                                  
  ### Step 8: Push and explain alerts                                                                                             
                                                                                                                                  
  After the transaction succeeds:                                                                                                 
                                                                                                                                  
  - Alerts are pushed to connected WebSocket clients.                                                                             
  - AI explanation jobs are scheduled in the background.                                                                          
                                                                                                                                  
  This ensures the dashboard never receives an alert that later rolls back.                                                       
                                                                                                                                  
  ## 5. Detection rules                                                                                                           
                                                                                                                                  
  ### Brute-force detection                                                                                                       
                                                                                                                                  
  Implemented in backend/app/detection/rules/brute_force.py.                                                                      
                                                                                                                                  
  It tracks failed logins per user inside a 60-second sliding window.                                                             
                                                                                                                                  
  Thresholds:                                                                                                                     
                                                                                                                                  
  5 failures   → MEDIUM, score 45                                                                                                 
  10 failures  → HIGH, score 70                                                                                                   
  20 failures  → CRITICAL, score 90                                                                                               
                                                                                                                                  
  It emits only when a new threshold is crossed, avoiding duplicate alerts on every subsequent failed login.                      
                                                                                                                                  
  If a successful login occurs while the failure burst is active, it emits:                                                       
                                                                                                                                  
  brute_force_success → CRITICAL                                                                                                  
                                                                                                                                  
  That represents a possible successful compromise.                                                                               
                                                                                                                                  
  The detector uses a threading.Lock because FastAPI runs the synchronous ingestion endpoint across worker threads.               
                                                                                                                                  
  ### Port-scan detection                                                                                                         
                                                                                                                                  
  Implemented in backend/app/detection/rules/port_scan.py.                                                                        
                                                                                                                                  
  It tracks source IPs and distinct ports touched within three seconds.                                                           
                                                                                                                                  
  Thresholds:                                                                                                                     
                                                                                                                                  
  15 distinct ports → HIGH                                                                                                        
  50 distinct ports → CRITICAL                                                                                                    
                                                                                                                                  
  Repeated access to the same port does not increase the distinct-port count.                                                     
                                                                                                                                  
  ### Unusual-IP detection                                                                                                        
                                                                                                                                  
  Implemented in backend/app/detection/rules/unusual_ip.py.                                                                       
                                                                                                                                  
  The first three login events establish a user’s baseline.                                                                       
                                                                                                                                  
  After that, a login from an unseen IP creates a low-severity alert.                                                             
                                                                                                                                  
  The IP is then added to the user’s known-IP list.                                                                               
                                                                                                                                  
  ## 6. Sliding windows                                                                                                           
                                                                                                                                  
  backend/app/detection/sliding_window.py provides the reusable time-window structure.                                            
                                                                                                                                  
  It uses a deque, which gives efficient:                                                                                         
                                                                                                                                  
  - Append operations                                                                                                             
  - Old-event eviction                                                                                                            
  - Counting                                                                                                                      
  - Distinct-value extraction                                                                                                     
                                                                                                                                  
  Eviction is based on event timestamps rather than server wall-clock time, which makes tests deterministic.                      
                                                                                                                                  
  The detector windows are in-memory. This works for one backend process, but would need Redis or another shared store for        
  multiple backend instances.                                                                                                     
                                                                                                                                  
  ## 7. Behavioral profiling                                                                                                      
                                                                                                                                  
  The profiler is implemented in backend/app/profiling/profiler.py.                                                               
                                                                                                                                  
  It uses exponential moving averages with:                                                                                       
                                                                                                                                  
  EMA_ALPHA = 0.05                                                                                                                
                                                                                                                                  
  The profile learns:                                                                                                             
                                                                                                                                  
  - Typical login hour                                                                                                            
  - Login-time variance                                                                                                           
  - Typical days between logins                                                                                                   
  - Average session duration                                                                                                      
  - Known IPs                                                                                                                     
                                                                                                                                  
  The profiler does not currently create alerts by itself. It produces contextual information that influences scoring and supports
  the unusual-IP detector.                                                                                                        
                                                                                                                                  
  Despite some older documentation mentioning Isolation Forest, there is no active Isolation Forest implementation in the current 
  code. The actual behavioral model is heuristic/EMA-based.                                                                       
                                                                                                                                  
  ## 8. Risk scoring                                                                                                              
                                                                                                                                  
  Risk scoring has two separate concepts.                                                                                         
                                                                                                                                  
  ### Event/alert score                                                                                                           
                                                                                                                                  
  This answers:                                                                                                                   
                                                                                                                                  
  > How dangerous is this individual alert?                                                                                       
                                                                                                                                  
  The raw detector score is adjusted using behavioral deviation:                                                                  
                                                                                                                                  
  adjusted =                                                                                                                      
  base_score                                                                                                                      
  + deviation_score × DEVIATION_WEIGHT × (100 - base_score)                                                                       
                                                                                                                                  
  The default deviation weight is 0.3.                                                                                            
                                                                                                                                  
  Example:                                                                                                                        
                                                                                                                                  
  Base score:       70                                                                                                            
  Deviation:        1.0                                                                                                           
  Weight:           0.3                                                                                                           
                                                                                                                                  
  Adjusted score = 70 + 1.0 × 0.3 × 30                                                                                            
                 = 79                                                                                                             
                                                                                                                                  
  That crosses the 75 threshold and becomes CRITICAL.                                                                             
                                                                                                                                  
  The score is clamped between 0 and 100, then severity is recalculated.                                                          
                                                                                                                                  
  Implemented in backend/app/scoring/risk_scorer.py.                                                                              
                                                                                                                                  
  ### User risk score                                                                                                             
                                                                                                                                  
  This answers:                                                                                                                   
                                                                                                                                  
  > How concerning is this user’s overall recent pattern?                                                                         
                                                                                                                                  
  Each new alert contributes to the profile’s cumulative score:                                                                   
                                                                                                                                  
  new_user_score =                                                                                                                
  old_score × 0.995                                                                                                               
  + adjusted_alert_score × 0.15                                                                                                   
                                                                                                                                  
  The result is capped at 100.                                                                                                    
                                                                                                                                  
  This is what powers:                                                                                                            
                                                                                                                                  
  GET /api/v1/users/high-risk                                                                                                     
                                                                                                                                  
  ### Time-based decay                                                                                                            
                                                                                                                                  
  The project also includes scheduled decay in backend/app/scoring/decay_job.py.                                                  
                                                                                                                                  
  The formula is:                                                                                                                 
                                                                                                                                  
  decayed_score =                                                                                                                 
  current_score × 0.98 ^ days_elapsed                                                                                             
                                                                                                                                  
  This prevents a user from remaining high-risk forever after one old incident.                                                   
                                                                                                                                  
  Decay runs:                                                                                                                     
                                                                                                                                  
  - On startup                                                                                                                    
  - Every 24 hours                                                                                                                
  - Manually through /api/v1/admin/decay-now                                                                                      
                                                                                                                                  
  The manual admin endpoint is not authentication-protected yet.                                                                  
                                                                                                                                  
  ## 9. Database models                                                                                                           
                                                                                                                                  
  The ORM models are in backend/app/models.                                                                                       
                                                                                                                                  
  ### User                                                                                                                        
                                                                                                                                  
  Stores:                                                                                                                         
                                                                                                                                  
  - Internal UUID                                                                                                                 
  - External user_id                                                                                                              
  - First-seen timestamp                                                                                                          
  - Last-seen timestamp                                                                                                           
                                                                                                                                  
  ### LogEvent                                                                                                                    
                                                                                                                                  
  Stores:                                                                                                                         
                                                                                                                                  
  - User                                                                                                                          
  - IP                                                                                                                            
  - Timestamp                                                                                                                     
  - Event type                                                                                                                    
  - Status                                                                                                                        
  - Port                                                                                                                          
  - Endpoint                                                                                                                      
  - User agent                                                                                                                    
  - Country                                                                                                                       
  - Original raw JSON                                                                                                             
                                                                                                                                  
  ### BehaviorProfile                                                                                                             
                                                                                                                                  
  Stores one mutable baseline row per user.                                                                                       
                                                                                                                                  
  ### Alert                                                                                                                       
                                                                                                                                  
  Stores:                                                                                                                         
                                                                                                                                  
  - Alert type                                                                                                                    
  - Final severity                                                                                                                
  - Final score                                                                                                                   
  - Raw detector severity                                                                                                         
  - Raw detector score                                                                                                            
  - Human-readable detector message                                                                                               
  - Triggering event ID                                                                                                           
  - AI explanation                                                                                                                
  - Mitigation steps                                                                                                              
  - Resolved state                                                                                                                
  - Resolution timestamp                                                                                                          
  - Creation timestamp                                                                                                            
                                                                                                                                  
  Database schema changes are managed through Alembic migrations in backend/alembic/versions.                                     
                                                                                                                                  
  ## 10. AI explainability                                                                                                        
                                                                                                                                  
  The AI layer is in backend/app/ai.                                                                                              
                                                                                                                                  
  When an alert is generated:                                                                                                     
                                                                                                                                  
  1. The alert is committed immediately.                                                                                          
  2. A background task loads the alert and user profile.                                                                          
  3. A prompt is sent to Ollama.                                                                                                  
  4. Mistral returns:                                                                                                             
      - Explanation                                                                                                               
      - Mitigation checklist                                                                                                      
                                                                                                                                  
  5. The alert row is updated.                                                                                                    
                                                                                                                                  
  AI generation does not block log ingestion.                                                                                     
                                                                                                                                  
  If Ollama is unavailable:                                                                                                       
                                                                                                                                  
  - The alert is still stored.                                                                                                    
  - explanation and mitigation_steps remain null.                                                                                 
  - The system does not fabricate an explanation.                                                                                 
                                                                                                                                  
  Important limitation: failed explanations are not retried. An alert can remain unexplained permanently unless generation is     
  manually re-triggered through future functionality.                                                                             
                                                                                                                                  
  ## 11. Chatbot                                                                                                                  
                                                                                                                                  
  The chatbot endpoint is:                                                                                                        
                                                                                                                                  
  POST /api/v1/chat                                                                                                               
                                                                                                                                  
  The frontend sends:                                                                                                             
                                                                                                                                  
  {                                                                                                                               
    "session_id": "some-session-id",                                                                                              
    "message": "What happened with alice recently?"                                                                               
  }                                                                                                                               
                                                                                                                                  
  The chatbot gathers recent alert context and gives it to Ollama so responses are grounded in current ThreatLens data.           
                                                                                                                                  
  The frontend keeps the session ID in React state. A browser reload starts a new conversation.                                   
                                                                                                                                  
  The dashboard widget and full Assistant page share the same conversation through frontend/src/context/ChatContext.jsx.          
                                                                                                                                  
  ## 12. WebSockets                                                                                                               
                                                                                                                                  
  The WebSocket endpoint is:                                                                                                      
                                                                                                                                  
  /ws/alerts                                                                                                                      
                                                                                                                                  
  The manager is implemented in backend/app/realtime/websocket_manager.py.                                                        
                                                                                                                                  
  The ingestion endpoint is synchronous, but WebSocket broadcasting is asynchronous. The system bridges those two execution models
  using the main event loop.                                                                                                      
                                                                                                                                  
  The frontend:                                                                                                                   
                                                                                                                                  
  - Fetches existing alerts initially                                                                                             
  - Opens a WebSocket                                                                                                             
  - Prepends newly pushed alerts                                                                                                  
  - Reconnects with exponential backoff                                                                                           
  - Keeps at most 200 alerts in memory                                                                                            
  - Periodically re-fetches alerts to backfill AI explanations                                                                    
                                                                                                                                  
  If the WebSocket disconnects, the frontend retries automatically.                                                               
                                                                                                                                  
  ## 13. Frontend pages                                                                                                           
                                                                                                                                  
  The frontend entry point is frontend/src/App.jsx.                                                                               
                                                                                                                                  
  Available routes:                                                                                                               
                                                                                                                                  
  /            Dashboard                                                                                                          
  /alerts      Alert history                                                                                                      
  /users       User analytics                                                                                                     
  /assistant   Full-page AI assistant                                                                                             
                                                                                                                                  
  ### Dashboard                                                                                                                   
                                                                                                                                  
  The Dashboard includes:                                                                                                         
                                                                                                                                  
  - Connection status                                                                                                             
  - Summary cards                                                                                                                 
  - Threat activity chart                                                                                                         
  - Severity breakdown donut chart                                                                                                
  - Live alert feed                                                                                                               
  - Chat widget                                                                                                                   
  - High-risk users panel                                                                                                         
                                                                                                                                  
  The dashboard uses the WebSocket alert stream.                                                                                  
                                                                                                                                  
  Its charts are calculated from the alerts currently loaded in browser memory, not from database-wide aggregate queries.         
                                                                                                                                  
  ### Alerts page                                                                                                                 
                                                                                                                                  
  The Alerts page supports:                                                                                                       
                                                                                                                                  
  - Severity filtering                                                                                                            
  - Resolved/unresolved filtering                                                                                                 
  - Alert-type filtering                                                                                                          
  - Sorting by creation time or score                                                                                             
  - Resolve/unresolve actions                                                                                                     
                                                                                                                                  
  It uses normal REST requests rather than a persistent WebSocket.                                                                
                                                                                                                                  
  The result is capped at 100 records. There is no true page-number/offset pagination yet.                                        
                                                                                                                                  
  ### User Analytics                                                                                                              
                                                                                                                                  
  The User Analytics page allows an analyst to:                                                                                   
                                                                                                                                  
  - Search for a user                                                                                                             
  - Inspect risk score                                                                                                            
  - Inspect deviation score                                                                                                       
  - See login count                                                                                                               
  - See session count                                                                                                             
  - See known IPs                                                                                                                 
  - See login-time baseline                                                                                                       
  - See average session duration                                                                                                  
  - See that user’s alert history                                                                                                 
                                                                                                                                  
  There is no historical risk-score chart because only the current score is stored.                                               
                                                                                                                                  
  ### Assistant                                                                                                                   
                                                                                                                                  
  The Assistant page provides the full chatbot interface and shares state with the dashboard widget.                              
                                                                                                                                  
  ## 14. API summary                                                                                                              
                                                                                                                                  
   Method    Endpoint                           Purpose                                                                           
  ━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━                                                       
   POST      /api/v1/log                        Ingest a log event                                                                
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   GET       /api/v1/alerts                     Query alerts                                                                      
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   PATCH     /api/v1/alerts/{id}/resolve        Resolve an alert                                                                  
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   PATCH     /api/v1/alerts/{id}/unresolve      Reopen an alert                                                                   
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   GET       /api/v1/users/high-risk            List highest-risk users                                                           
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   GET       /api/v1/users/{user_id}/profile    Inspect one profile                                                               
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   POST      /api/v1/chat                       Ask the AI assistant                                                              
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   POST      /api/v1/admin/decay-now            Manually decay risk scores                                                        
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   GET       /health                            Health check                                                                      
  ────────  ─────────────────────────────────  ────────────────────────────                                                       
   WS        /ws/alerts                         Live alert stream                                                                 
                                                                                                                                  
  ## 15. Test coverage                                                                                                            
                                                                                                                                  
  The backend has approximately 172 test functions covering:                                                                      
                                                                                                                                  
  - Health checks                                                                                                                 
  - Log ingestion                                                                                                                 
  - Alert querying                                                                                                                
  - Alert resolution                                                                                                              
  - Brute-force detection                                                                                                         
  - Port scanning                                                                                                                 
  - Unusual IPs                                                                                                                   
  - Sliding windows                                                                                                               
  - Thread concurrency                                                                                                            
  - Behavioral profiling                                                                                                          
  - Risk scoring                                                                                                                  
  - Risk decay                                                                                                                    
  - WebSockets                                                                                                                    
  - Ollama failure behavior                                                                                                       
  - AI explanations                                                                                                               
  - Chatbot behavior                                                                                                              
                                                                                                                                  
  I attempted to run the backend test suite, but it did not finish within the available run window and was stopped. The frontend  
  build could not run because frontend dependencies are not currently installed—vite was unavailable.                             
                                                                                                                                  
  ## 16. What is genuinely implemented                                                                                            
                                                                                                                                  
  Implemented:                                                                                                                    
                                                                                                                                  
  - Structured log ingestion                                                                                                      
  - PostgreSQL persistence                                                                                                        
  - Three detection rules                                                                                                         
  - Behavioral profiles                                                                                                           
  - Context-aware alert scoring                                                                                                   
  - Rolling user risk scoring                                                                                                     
  - Time-based risk decay                                                                                                         
  - Alert resolution                                                                                                              
  - AI explanation generation                                                                                                     
  - AI chatbot                                                                                                                    
  - WebSocket alert delivery                                                                                                      
  - React dashboard                                                                                                               
  - User analytics                                                                                                                
  - Automated backend tests                                                                                                       
                                                                                                                                  
  ## 17. Main limitations                                                                                                         
                                                                                                                                  
  The most important limitations are:                                                                                             
                                                                                                                                  
  - No authentication or authorization                                                                                            
  - Admin decay endpoint is publicly callable                                                                                     
  - No rate limiting                                                                                                              
  - Detector state is process-local                                                                                               
  - Multiple backend replicas would not share sliding-window state                                                                
  - AI explanations have no retry mechanism                                                                                       
  - AI explanation jobs use FastAPI background tasks rather than a durable queue                                                  
  - No historical risk-score table                                                                                                
  - Alert page has a hard cap instead of real pagination                                                                          
  - Dashboard charts summarize only the in-memory alert window                                                                    
  - No automated IP blocking or response action                                                                                   
  - No Isolation Forest or trained ML model currently exists                                                                      
  - Risk weights are static                                                                                                       
  - Chat sessions are lost on browser reload                                                                                      
  - Documentation has some stale phase-status text that says WebSockets are not started, even though the WebSocket implementation 
    is present                                                                                                                    
                                                                                                                                  
  In short: ThreatLens is a strong academic prototype demonstrating the complete path from raw security events to contextual      
  detection, risk prioritization, explanation, and analyst visualization. Its main gap is production hardening and horizontal     
  scalability, not the core end-to-end functionality.
