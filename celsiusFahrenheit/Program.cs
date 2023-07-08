class Program
{
    static void Main()
    {
        //explicando para que serve o programa
        Console.WriteLine("=== Esse programa converte celsius em Fahrenheit ===");
        Console.Write("Digite uma temperatura: ");
        //criei uma variavel para receber o que a pessoa digitou
        double celsius = double.Parse(Console.ReadLine());
        double fahrenheit = 0;
        
        //calculando a temperatura de celsius para fahrenheit e salvando o resultado na variavel fahrenheit
        fahrenheit = celsius * 1.8 + 32;

        //entregando o resultado na tela
        Console.WriteLine("Resultado em fahrenheit: " + fahrenheit);
        Console.ReadKey();

    }
}

