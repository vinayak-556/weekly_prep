from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from typing import List
from weekly.tools.calendar_tool import FetchUpcomingMeetingsTool
from weekly.tools.gmail_tool import GmailMeetingTool
from weekly.tools.slack_tool import SlackDMTool
from weekly.tools.doc_tool import  GoogleDocTool
from weekly.tools.hubspot_tool import HubSpotSearchTool

@CrewBase
class Weekly():
    """Weekly crew"""
    agents: List[BaseAgent]
    tasks: List[Task]
    @agent
    def calendar_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['calendar_agent'],
            tools=[FetchUpcomingMeetingsTool()],
            verbose=True,
            allow_delegation=False,
            memory=True
           
            
               )

    @agent
    def gmail_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['gmail_agent'],
            tools=[GmailMeetingTool()],
            verbose=True,
            allow_delegation=False,
            memory=True  
            )
    
    @agent
    def hubspot_agent(self) -> Agent:
        return Agent(
            config=self.agents_config['hubspot_agent'],
            tools=[HubSpotSearchTool()],
            verbose=True,
            allow_delegation=False,
            memory=True
                       
            )
    
    @agent 
    def summary_agent(self) -> Agent:
        return Agent(
            config = self.agents_config['summary_agent'],
            verbose=True,
            allow_delegation=False,
            memory=True
            
                 )

    @agent
    def google_doc_agent(self) -> Agent:
        return Agent(
            config= self.agents_config['google_doc_agent'],
            tools = [GoogleDocTool()],
            verbose=True,

        )
    
    
    @agent
    def slack_notification_agent(self) -> Agent:
        return Agent(
            config= self.agents_config['slack_notification_agent'],
            tools=[SlackDMTool()],
            verbose=True,
            memory=True
            
          
            )

    @task
    def calendar_task(self) -> Task:
        return Task(
            config=self.tasks_config['calendar_task']
        )

    @task
    def gmail_task(self) -> Task:
        return Task(
            config=self.tasks_config['gmail_task'],   
        )
    
    @task
    def hubspot_task(self) -> Task:
        return Task(
            config=self.tasks_config['hubspot_task'],   
        )

    @task
    def summary_task(self) -> Task:
        return Task(
            config=self.tasks_config['summary_task'],        
        )
    
    @task
    def google_doc_task(self) -> Task:
        return Task(
            config=self.tasks_config['google_doc_task']
        )
    
    @task
    def slack_task(self) -> Task:
        return Task(
            config=self.tasks_config['slack_notification_task']
          )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True
                   )
 