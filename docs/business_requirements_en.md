# ZETOM CRM Business Logic (v.0.3)

**Document Purpose:** Agreement on lead processing architecture, notification systems, and responsibility distribution (Role Model).

---

## 1. Request Lifecycle

The control process in the system is divided into two independent levels. This allows for a clear distinction between the global "relevance" of a client and the current operational stage of work.

### 1.1. Global Statuses (Relevance)
Define whether the client is currently being handled:
* **Active:** The request is being processed (in any of the four cycles).
* **Archive:** Work is completed or forcibly stopped. Data is "frozen" for history and analytics.

### 1.2. Operational Cycles and Statuses
Each stage (cycle) is a separate workspace with its own documents. Within the current cycle, a request passes through the following states:
* **New:** The stage has just started; no active steps have been taken yet.
* **In Progress:** A specialist has started editing data or entered new information.
* **Waiting:** The system has logged an email sent to the client and is awaiting feedback.
* **Done:** Work on the current cycle/document is fully completed.

---

## 2. NULL Cycle: Sanitary Buffer and Data Protection

**NULL** is the primary buffer for all incoming inquiries from the website.

**Purpose in the system:**
1. **Spam Filtering:** A specialist filters out spam and "empty" requests before they enter the main operational department (Oferta).
2. **Duplicate Control:** The system checks Phone, Email, and Tax ID (NIP) in the background. By the time a specialist opens the request, the system already displays a verdict: "Clear" or "Duplicate found" (with a link to the original).

---

## 3. Role Model: Distribution of Responsibility

### 3.1. Access Hierarchy
The system is built on a strict hierarchy:
**Director (Admin) > Department Head > Specialist**

### 3.2. Special Roles
These roles exist outside the main hierarchy to solve specific tasks:
* **Custom User:** A role with dynamic permissions (configured per task). Cannot exceed Admin rights but can be equal (e.g., for a deputy).
* **Auditor:** A technical role for the developer. **No editing rights.** Access is limited to logs and incident reports to monitor system integrity.

### 3.3. Permissions Table
| Role | Business Meaning | Access Level |
| :--- | :--- | :--- |
| **Director (Admin)** | System Owner | Maximum access. Management of all requests, logs, and user accounts. |
| **Custom User** | Trusted Person | Flexible role for management tasks, with permissions set "above average." |
| **Department Head** | Dispatcher / Controller | Sees requests of their department. Assigns specialists. Monitors deadlines. |
| **Specialist** | Operator / Executor | Sees only those requests assigned personally by the head or admin. |
| **Auditor** | Tech Control | Read-only mode for technical auditing of the system. |

---

## 4. Notification and Control System (Points for Approval)

To set up effective communication, we need to define notification triggers:

1. **Primary Assignment:**
   - Request lands in NULL → Notification to Department Head for distribution.
   - Head assigns a Specialist → Notification to the Specialist.

2. **Change Control:**
   - Do you or the Department Head need to be notified of every intermediate change (`In Progress` status)?
   - Or is a notification upon the actual completion of key stages (`Done` status at the end of a cycle) sufficient?

3. **Critical Information:**
   - Is an immediate notification to management (Director or Custom User) required if a request is moved to **Archive** status?

---

### Summary for Confirmation:
1. Do you agree with the role of the "NULL Cycle" as a filter for new requests?
2. Are you satisfied with the availability of a Custom Role for flexible access settings (e.g., for a deputy)?
3. In which cases do you personally wish to receive notifications regarding request movement (Section 4)?
4. Do you agree with the separation of Global Statuses (Request) and Operational Statuses (within a cycle)?
5. Do you agree with the Lifecycle Diagram (attached to the message)?